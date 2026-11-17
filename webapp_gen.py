"""Транспорт «вебапп → бот» по HTTP вместо tg.sendData (docs/specs/2026-11-16_webapp_gen_transport.md).

sendData закрывает Mini App, поэтому конструкторы выкидывали юзера в чат.
Теперь вебапп кладёт тот же payload в очередь D1 (/api/gen/submit), бот
поллит её (/api/gen/poll) и скармливает существующим обработчикам
`apply_webapp_prompt_payload_v2` через синтетический Update. Вся логика
(валидация, биллинг, отмена, прогресс) остаётся прежней — меняется только
способ доставки и то, что кнопка вебаппа сама является подтверждением трат
(карточка «Запустить» в чате пропускается — см. is_autostart()).

Модуль не импортирует SirNike.py (цикл) — зависимости идут через configure().
"""

import asyncio
import contextvars
import datetime
import json
import logging
from typing import Awaitable, Callable, List, Optional

import aiohttp
from telegram import Chat, Message, Update, User
from telegram.ext import Application, CallbackContext

from config import STUDIO_POLL_SECRET, WEBAPP_GEN_API_BASE, WEBAPP_GEN_ENABLED, WEBAPP_GEN_POLL_INTERVAL
from db import get_studio_done_job, record_studio_done_job

logger = logging.getLogger(__name__)

_autostart: contextvars.ContextVar[bool] = contextvars.ContextVar("webapp_gen_autostart", default=False)
_job_id: contextvars.ContextVar[str] = contextvars.ContextVar("webapp_gen_job_id", default="")
_launched: contextvars.ContextVar[Optional[list]] = contextvars.ContextVar("webapp_gen_launched", default=None)
_replies: contextvars.ContextVar[Optional[list]] = contextvars.ContextVar("webapp_gen_replies", default=None)

_active_job_ids: set = set()

_apply_payload_hook: Optional[Callable[..., Awaitable[bool]]] = None
_ensure_user_hook: Callable[[int, str], None] = lambda user_id, username: None


def configure(apply_payload: Callable[..., Awaitable[bool]], ensure_user: Callable[[int, str], None]) -> None:
    global _apply_payload_hook, _ensure_user_hook
    _apply_payload_hook = apply_payload
    _ensure_user_hook = ensure_user


def is_autostart() -> bool:
    """True только внутри задания из очереди вебаппа: кнопка «Создать» в
    вебаппе уже показала цену и является подтверждением — карточку в чате
    пропускаем. Из sendData-пути всегда False."""
    return _autostart.get()


def current_job_id() -> str:
    return _job_id.get()


def mark_launched() -> None:
    """Обработчик зовёт, когда генерация реально запущена (а не отказ/валидация)."""
    flag = _launched.get()
    if flag is not None:
        flag.append(True)


def add_reply(text: str) -> None:
    """Причина отказа из callback-обработчика (query.answer) — вебаппу."""
    sink = _replies.get()
    if sink is not None:
        sink.append(str(text))


class _SinkMessage(Message):
    """Обычное сообщение чата + копия текстов ответов, чтобы вернуть причину
    отказа («нужно фото…», «не хватает изюминок») вебаппу, а не только в чат."""

    async def reply_text(self, text, *args, **kwargs):
        sink = _replies.get()
        if sink is not None:
            sink.append(str(text))
        return await super().reply_text(text, *args, **kwargs)


def _build_update(app: Application, user_id: int, username: str):
    user = User(id=user_id, first_name=username or str(user_id), is_bot=False, username=username or None)
    chat = Chat(id=user_id, type=Chat.PRIVATE)
    msg = _SinkMessage(message_id=0, date=datetime.datetime.now(datetime.timezone.utc), chat=chat, from_user=user)
    msg.set_bot(app.bot)
    update = Update(update_id=0, message=msg)
    update.set_bot(app.bot)
    return update, CallbackContext.from_update(update, app)


async def _api(path: str, payload: dict, timeout: int = 20) -> Optional[dict]:
    url = f"{WEBAPP_GEN_API_BASE}/{path.lstrip('/')}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                headers={"X-Studio-Secret": STUDIO_POLL_SECRET, "Content-Type": "application/json"},
                json=payload,
                timeout=aiohttp.ClientTimeout(total=timeout),
            ) as resp:
                if not (200 <= resp.status < 300):
                    logger.warning("webapp_gen api %s: status=%s", path, resp.status)
                    return None
                return await resp.json()
    except Exception as e:
        logger.warning("webapp_gen api %s exception: %s", path, e)
        return None


async def _complete(job_id: str, status: str, error: str = "", result: Optional[dict] = None) -> bool:
    payload = {"job_id": job_id, "status": status, "error": error, "result": result or {}}
    for attempt in range(3):
        if await _api("complete", payload) is not None:
            return True
        await asyncio.sleep(2 * (attempt + 1))
    logger.warning("webapp_gen complete undelivered for job=%s", job_id)
    return False


async def _handle_job(app: Application, job: dict) -> None:
    job_id = str(job.get("id") or "")
    user_id = int(job.get("user_id") or 0)
    payload = job.get("payload") or {}
    if isinstance(payload, str):
        try:
            payload = json.loads(payload or "{}")
        except json.JSONDecodeError:
            payload = {}
    if not job_id or not user_id or not isinstance(payload, dict) or not payload:
        if job_id:
            await _complete(job_id, "error", "bad_job")
        return

    # Идемпотентность. Уже завершён — только повторная доставка результата.
    # Помечен «started» (бот упал посреди обработки) — НЕ запускаем повторно:
    # обработчик может списывать изюминки, лучше отказ, чем двойная трата.
    done = get_studio_done_job(job_id)
    if done:
        if done["status"] in ("done", "error"):
            await _complete(job_id, done["status"], done["error"], json.loads(done["result"] or "{}"))
        else:
            record_studio_done_job(job_id, user_id, False, 0, "error", "interrupted", "{}")
            await _complete(job_id, "error", "interrupted")
        return
    record_studio_done_job(job_id, user_id, False, 0, "started", "", "{}")

    username = str(job.get("username") or "")
    replies: List[str] = []
    launched: list = []
    _autostart.set(True)
    _job_id.set(job_id)
    _replies.set(replies)
    _launched.set(launched)
    status, error, ok = "error", "internal", False
    try:
        _ensure_user_hook(user_id, username)
        update, context = _build_update(app, user_id, username)
        ok = bool(await _apply_payload_hook(update, context, payload))
        status, error = ("done", "") if launched else ("error", "not_started")
    except Exception:
        logger.exception("webapp_gen job %s crashed", job_id)
    result = {
        "accepted": ok,
        "launched": bool(launched),
        "product": str(payload.get("product") or ""),
        "progress_id": job_id if launched else "",
        "messages": replies[:3],
    }
    record_studio_done_job(job_id, user_id, False, 0, status, error, json.dumps(result, ensure_ascii=False))
    await _complete(job_id, status, error, result)


async def _run_job(app: Application, job: dict) -> None:
    try:
        await _handle_job(app, job)
    except Exception:
        logger.exception("webapp_gen job crashed: %s", job.get("id"))
    finally:
        _active_job_ids.discard(str(job.get("id") or ""))


async def poll_loop(app: Application) -> None:
    logger.info("webapp_gen poll loop started: %s (every %ss)", WEBAPP_GEN_API_BASE, WEBAPP_GEN_POLL_INTERVAL)
    while True:
        try:
            data = await _api("poll", {"limit": 5})
            for job in (data or {}).get("jobs") or []:
                jid = str(job.get("id") or "")
                if jid and jid not in _active_job_ids:
                    _active_job_ids.add(jid)
                    asyncio.create_task(_run_job(app, job))
        except Exception:
            logger.exception("webapp_gen poll loop error")
        await asyncio.sleep(WEBAPP_GEN_POLL_INTERVAL)
