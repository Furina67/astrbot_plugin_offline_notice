# -*- coding: utf-8 -*-
"""
QQ 主动提醒模块

作用：当被监控的 bot 掉线 / 恢复时，通过「另一个机器人」向指定 QQ 号私聊推送提醒。

发送通道（按优先级）：
1. OneBot v11（aiocqhttp / NapCat）—— 拿到平台实例后用 send_private_msg 直发私聊。
2. QQ 官方机器人（qq_official）—— 走 AstrBot 跨平台通用接口
   context.send_message(unified_msg_origin, chain)，需要先知道会话 UMO。
3. UMO 自动记忆 —— 机器人收到任何私聊消息时，插件会把该会话 UMO 持久化到
   data_dir/qq_notifier_umo.json，之后主动推送直接复用，无需手工填写。

注意：QQ 官方机器人的主动消息要求用户先与机器人建立会话（主动私聊一次即可）。
"""

import asyncio
import json
import re
from datetime import datetime
from typing import List, Optional

from astrbot.api import logger

# ---------------------------------------------------------------------------
# 默认提醒内容模板
# ---------------------------------------------------------------------------
DEFAULT_OFFLINE_PUSH_BODY = (
    "🔔 账号掉线提醒\n"
    "账号：{nickname}（{uin}）\n"
    "平台：{platform}\n"
    "时间：{time}\n"
    "状态：{event}\n"
    "{extra}"
)


class QQNotifier:
    """负责把提醒消息推送到指定 QQ 号。"""

    def __init__(self, plugin):
        # 持有插件实例，复用其 config 与 context
        self.plugin = plugin

    # -- 配置读取 ----------------------------------------------------------
    @property
    def _cfg(self) -> dict:
        return self.plugin.config.get("qq_reminder", {}) or {}

    def is_enabled(self) -> bool:
        if not self._cfg.get("enabled", False):
            return False
        return bool(self.get_target_qq_list())

    def get_target_qq_list(self) -> List[str]:
        """读取目标 QQ，兼容 list / 逗号分隔字符串两种写法。"""
        raw = self._cfg.get("target_qq", [])
        result: List[str] = []
        if isinstance(raw, str):
            raw = re.split(r"[,，\s]+", raw)
        if isinstance(raw, (list, tuple, set)):
            for item in raw:
                item = str(item).strip()
                if item.isdigit():
                    result.append(item)
        # 去重保序
        seen = set()
        return [q for q in result if not (q in seen or seen.add(q))]

    def get_platform_id(self) -> str:
        """只发指定平台实例；留空表示自动挑选第一个可用的 aiocqhttp 实例。"""
        return str(self._cfg.get("platform_id", "") or "").strip()

    def get_body_template(self) -> str:
        tpl = self._cfg.get("content", "")
        if not tpl or not tpl.strip():
            tpl = DEFAULT_OFFLINE_PUSH_BODY
        return tpl

    def get_prefix(self) -> str:
        return str(self._cfg.get("prefix", "") or "")

    # -- 模板渲染 ----------------------------------------------------------
    @staticmethod
    def _render(template: str, vars_: dict) -> str:
        def _rep(m):
            key = m.group(1).strip()
            return str(vars_.get(key, m.group(0)))

        # 同时支持 {key} 与 {{key}}
        out = re.sub(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}", _rep, template)
        out = re.sub(r"(?<!\{)\{\s*([a-zA-Z0-9_]+)\s*\}(?!\})", _rep, out)
        return out

    def build_message(self, *, nickname: str, uin: str, platform: str,
                      event: str, time_str: str, extra: str = "") -> str:
        body = self._render(
            self.get_body_template(),
            {
                "nickname": nickname,
                "uin": uin,
                "platform": platform,
                "event": event,
                "time": time_str,
                "extra": extra,
            },
        )
        prefix = self.get_prefix()
        # OneBot v11 会 strip 掉首尾空白/换行，用零宽字符保住格式
        if prefix:
            body = f"{prefix}{body}"
        return "\u200b" + body + "\u200b"

    # -- UMO 存储（用于 QQ 官方机器人 / 跨平台主动消息） --------------------
    def _umo_file(self):
        """UMO 持久化文件路径。"""
        try:
            data_dir = self.plugin.data_dir
            return data_dir / "qq_notifier_umo.json"
        except Exception:
            return None

    def _load_umo_store(self) -> dict:
        path = self._umo_file()
        if path is None:
            return {}
        try:
            if path.exists():
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    out = {}
                    for k, v in data.items():
                        if isinstance(v, dict):
                            v.setdefault("umo", k)
                            v.setdefault("count", 0)
                            v.setdefault("ts", 0)
                            out[k] = v
                        else:
                            out[k] = {"umo": k, "count": 0, "ts": 0}
                    return out
        except Exception as e:
            logger.warning(f"[QQ提醒] 读取 UMO 存储失败: {e}")
        return {}

    def _save_umo_store(self, store: dict):
        path = self._umo_file()
        if path is None:
            return
        try:
            tmp = path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(store, f, ensure_ascii=False, indent=2)
            tmp.replace(path)
        except Exception as e:
            logger.warning(f"[QQ提醒] 保存 UMO 存储失败: {e}")

    def remember_umo(self, umo: str, sender_id: str = "", sender_name: str = "") -> bool:
        """记录一个可用会话的 UMO（收到私聊消息时调用）。"""
        if not self._cfg.get("auto_remember_umo", True):
            return False
        umo = str(umo or "").strip()
        if not umo:
            return False
        store = self._load_umo_store()
        prev = store.get(umo) or {}
        store[umo] = {
            "umo": umo,
            "sender_id": str(sender_id or prev.get("sender_id", "")),
            "sender_name": str(sender_name or prev.get("sender_name", "")),
            "count": int(prev.get("count", 0)) + 1,
            "ts": int(datetime.now().timestamp()),
        }
        self._save_umo_store(store)
        logger.info(f"[QQ提醒] 已记住会话 UMO: {umo}")
        return True

    def get_umo_list(self, with_platform: str = "") -> List[str]:
        """获取可用的 UMO 列表：先配置项，再自动记录的会话。"""
        result = []
        manual = str(self._cfg.get("umo", "") or "").strip()
        for part in manual.replace("，", ",").split(","):
            part = part.strip()
            if part and part not in result:
                result.append(part)

        store = self._load_umo_store()
        items = sorted(store.values(), key=lambda x: int(x.get("ts", 0)), reverse=True)
        wanted_targets = set(self.get_target_qq_list())
        for it in items:
            umo = str(it.get("umo", "")).strip()
            if not umo or umo in result:
                continue
            sender = str(it.get("sender_id", "")).strip()
            if wanted_targets and sender and sender not in wanted_targets:
                continue
            if with_platform:
                head = umo.split(":", 2)
                if len(head) >= 2 and head[1] and head[1] != with_platform:
                    continue
            result.append(umo)
        return result

    # -- 平台实例 ----------------------------------------------------------
    def _platform_kind(self, p) -> str:
        """判断平台实例类型：'onebot' / 'qqofficial' / '' 。"""
        cls_name = (p.__class__.__name__ or "").lower()
        inst_id = ""
        try:
            inst_id = str(p.meta().id) if hasattr(p, "meta") else ""
        except Exception:
            inst_id = ""
        blob = cls_name + " " + inst_id.lower()
        if "aiocqhttp" in blob or "onebot" in blob:
            return "onebot"
        if "qqofficial" in blob or "qq_official" in blob or "official" in blob:
            return "qqofficial"
        return ""

    def _iter_candidates(self):
        """遍历 OneBot v11（aiocqhttp）平台实例，支持按 platform_id 限定。"""
        try:
            platforms = self.plugin.context.platform_manager.get_insts()
        except Exception as e:
            logger.error(f"[QQ提醒] 获取平台实例失败: {e}")
            return []

        wanted = self.get_platform_id()
        candidates = []
        for p in platforms:
            inst_id = ""
            try:
                inst_id = str(p.meta().id) if hasattr(p, "meta") else ""
            except Exception:
                inst_id = ""
            if wanted and inst_id and inst_id != wanted:
                continue
            if self._platform_kind(p) == "onebot":
                candidates.append(p)

        if wanted and not candidates:
            for p in platforms:
                inst_id = ""
                try:
                    inst_id = str(p.meta().id) if hasattr(p, "meta") else ""
                except Exception:
                    pass
                if wanted in (inst_id, p.__class__.__name__):
                    candidates.append(p)
        return candidates

    def _iter_official(self):
        """遍历 QQ 官方机器人（qq_official）平台实例。"""
        try:
            platforms = self.plugin.context.platform_manager.get_insts()
        except Exception:
            return []
        return [p for p in platforms if self._platform_kind(p) == "qqofficial"]

    # -- 发送 --------------------------------------------------------------
    async def push(self, *, nickname: str, uin: str, platform: str,
                   event: str, extra: str = "") -> bool:
        """推送提醒：优先 OneBot 直发，其次 QQ 官方 / UMO 主动消息。"""
        if not self.is_enabled():
            logger.debug("[QQ提醒] 未启用或未配置目标 QQ，跳过")
            return False

        targets = self.get_target_qq_list()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        text = self.build_message(
            nickname=nickname, uin=uin, platform=platform,
            event=event, time_str=now, extra=extra,
        )

        # 1) OneBot v11（aiocqhttp / NapCat）直发私聊
        for p in self._iter_candidates():
            client = None
            try:
                client = p.get_client()
            except Exception as e:
                logger.warning(f"[QQ提醒] 获取客户端失败: {e}")
            api = getattr(client, "api", None) if client is not None else None
            if api is None:
                continue

            ok_any = False
            for qq in targets:
                try:
                    await api.call_action(
                        "send_private_msg", user_id=int(qq), message=text,
                    )
                    logger.info(f"[QQ提醒] 已通过 OneBot 推送到 QQ {qq}")
                    ok_any = True
                except Exception as e:
                    logger.error(f"[QQ提醒] OneBot 推送到 QQ {qq} 失败: {e}")
            if ok_any:
                return True

        # 2) QQ 官方机器人 / 跨平台 UMO 主动消息
        ok = await self._push_by_umo(targets, text)
        if ok:
            return True

        logger.error(
            "[QQ提醒] 全部通道均失败。请检查：①是否配置了可用的提醒机器人实例；"
            "②QQ 官方机器人需先让对方主动私聊一次以建立会话。"
        )
        return False

    async def _push_by_umo(self, targets: List[str], text: str) -> bool:
        """按 UMO 主动发送（跨平台通用，QQ 官方机器人主通道）。"""
        umos = self.get_umo_list()
        if not umos:
            logger.warning(
                "[QQ提醒] 没有可用的 UMO。若使用 QQ 官方机器人，请先私聊该机器人任意一句，"
                "插件会自动记录会话。"
            )
            return False

        try:
            from astrbot.api.message_components import Plain
            from astrbot.api.event import MessageChain
        except Exception as e:
            logger.error(f"[QQ提醒] 导入消息组件失败: {e}")
            return False

        chain = MessageChain().message(Plain(text))
        ok = False
        for umo in umos:
            try:
                await self.plugin.context.send_message(umo, chain)
                logger.info(f"[QQ提醒] 已通过 UMO 发送: {umo}")
                ok = True
            except Exception as e:
                logger.error(f"[QQ提醒] UMO 发送失败 {umo}: {e}")
        return ok

    # -- 自检指令用 --------------------------------------------------------
    async def send_test(self, extra_note: str = "") -> str:
        if not self._cfg.get("enabled", False):
            return "❌ QQ 提醒未开启，请先在配置中勾选「启用 QQ 号提醒」。"
        targets = self.get_target_qq_list()
        if not targets:
            return "❌ 还没有配置目标 QQ 号，请先在配置里填写要提醒的 QQ。"
        ok = await self.push(
            nickname="测试账号",
            uin="1000000000",
            platform="测试平台",
            event="测试提醒",
            extra=extra_note or "（这是一条测试消息，收到即表示配置正常 ✅）",
        )
        if ok:
            return f"✅ 测试提醒已推送到：{', '.join(targets)}"
        umos = self.get_umo_list()
        tip = ""
        if not umos:
            tip = "\n💡 若使用 QQ 官方机器人：请先私聊该机器人任意一句话，再执行本指令。"
        return (
            f"❌ 推送失败：目标 QQ {', '.join(targets)}。\n"
            "可能原因：目标不是提醒机器人的好友 / 平台实例填写有误 / 协议端离线。" + tip
        )

    def describe_status(self) -> str:
        """返回当前提醒通道的诊断信息。"""
        lines = []
        try:
            platforms = self.plugin.context.platform_manager.get_insts()
        except Exception as e:
            return f"获取平台实例失败: {e}"
        for p in platforms:
            kind = self._platform_kind(p)
            if not kind:
                continue
            inst_id = getattr(getattr(p, "meta", lambda: None)(), "id", "?")
            lines.append(f"- {inst_id}（{kind}）")
        umos = self.get_umo_list()
        text = "可用平台实例：\n" + ("\n".join(lines) if lines else "（无）")
        text += f"\n\n已记录 UMO：{len(umos)} 个"
        for u in umos:
            text += f"\n  · {u}"
        return text
