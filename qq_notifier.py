# -*- coding: utf-8 -*-
"""
QQ 主动提醒模块

作用：当被监控的 bot 掉线 / 恢复时，通过「另一个机器人」向指定 QQ 号私聊推送提醒。

核心难点与做法：
1. 跨平台实例发送 —— 不能用 event.unified_msg_origin（那是当前事件的会话），
   必须拿到目标平台实例，再用 aiocqhttp 的 send_private_msg 直接发。
2. UMO 兜底 —— 若目标平台实例拿不到 API，则用存储的 UMO 走 context.send_message。
3. 完全可配置 —— 目标 QQ、提醒内容、是否启用，全部走 _conf_schema.json。
"""

import asyncio
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

    # -- 平台实例 ----------------------------------------------------------
    def _iter_candidates(self):
        """遍历所有 aiocqhttp 平台实例，若指定了 platform_id 则优先/限定它。"""
        try:
            platforms = self.plugin.context.platform_manager.get_insts()
        except Exception as e:
            logger.error(f"[QQ提醒] 获取平台实例失败: {e}")
            return []

        wanted = self.get_platform_id()
        candidates = []
        for p in platforms:
            cls_name = p.__class__.__name__
            inst_id = ""
            try:
                inst_id = str(p.meta().id) if hasattr(p, "meta") else ""
            except Exception:
                inst_id = ""

            if wanted and inst_id and inst_id != wanted:
                continue
            # 只考虑 OneBot v11 系列（aiocqhttp / NapCat / Lagrange 都走这个适配器）
            if "aiocqhttp" in cls_name.lower() or "aiocqhttp" in inst_id.lower():
                candidates.append(p)

        if wanted and not candidates:
            # 指定了 id 但对不上，退化为全量匹配（避免用户填的是平台名）
            for p in platforms:
                inst_id = ""
                try:
                    inst_id = str(p.meta().id) if hasattr(p, "meta") else ""
                except Exception:
                    pass
                if wanted in (inst_id, p.__class__.__name__):
                    candidates.append(p)

        return candidates

    # -- 发送 --------------------------------------------------------------
    async def push(self, *, nickname: str, uin: str, platform: str,
                   event: str, extra: str = "") -> bool:
        """向所有配置的目标 QQ 推送提醒，返回是否至少有一个成功。"""
        if not self.is_enabled():
            logger.debug("[QQ提醒] 未启用或未配置目标 QQ，跳过")
            return False

        targets = self.get_target_qq_list()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        text = self.build_message(
            nickname=nickname, uin=uin, platform=platform,
            event=event, time_str=now, extra=extra,
        )

        ok_any = False
        for p in self._iter_candidates():
            client = None
            try:
                client = p.get_client()
            except Exception as e:
                logger.warning(f"[QQ提醒] 获取客户端失败: {e}")

            api = getattr(client, "api", None) if client is not None else None
            if api is None:
                continue

            for qq in targets:
                try:
                    await api.call_action(
                        "send_private_msg",
                        user_id=int(qq),
                        message=text,
                    )
                    logger.info(f"[QQ提醒] 已推送到 QQ {qq}")
                    ok_any = True
                except Exception as e:
                    logger.error(f"[QQ提醒] 推送到 QQ {qq} 失败: {e}")

            if ok_any:
                return True

        # 兜底：用 UMO 走 context.send_message
        if not ok_any:
            ok_any = await self._push_by_umo(targets, text)
        return ok_any

    async def _push_by_umo(self, targets: List[str], text: str) -> bool:
        """兜底方案：按 UMO 主动发送。需要用户预先配置 umo。"""
        umo = str(self._cfg.get("umo", "") or "").strip()
        if not umo:
            return False
        ok = False
        try:
            from astrbot.api.message_components import Plain
            from astrbot.api.event import MessageChain
            chain = MessageChain().message(Plain(text))
            await self.plugin.context.send_message(umo, chain)
            logger.info(f"[QQ提醒] 已通过 UMO 兜底发送: {umo}")
            ok = True
        except Exception as e:
            logger.error(f"[QQ提醒] UMO 兜底发送失败: {e}")
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
        return (
            f"❌ 推送失败：目标 QQ {', '.join(targets)}。\n"
            "可能原因：目标 QQ 不是提醒机器人所在平台的好友 / 未指定正确的平台实例 / 协议端离线。"
        )
