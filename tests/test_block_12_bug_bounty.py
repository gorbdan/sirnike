# -*- coding: utf-8 -*-
"""Блок 11: баг-баунти (reward_bug_)."""
import asyncio
import base64
import time
import types
from unittest.mock import AsyncMock

from test_helpers import S, make_update_context, make_text_update, OK_PNG_B64


def test_block_12_bug_bounty():
    ok_png_b64 = OK_PNG_B64

    _bb_target_id = 9601
    S.create_user_if_not_exists(_bb_target_id, "bugfinder", S.START_BONUS)
    _bal_before = S.get_balance(_bb_target_id)

    # 11.1: не-админ жмёт "Наградить" -> нет доступа, баланс не меняется
    update, context, query = make_update_context(f"reward_bug_{_bb_target_id}", user_id=9602)
    query.edit_message_reply_markup = AsyncMock()
    _orig_admin_ids = list(S.ADMIN_IDS)
    if 9602 in S.ADMIN_IDS:
        S.ADMIN_IDS.remove(9602)
    asyncio.run(S.button_handler(update, context))
    assert (query.answer.await_args_list
            and "доступ" in query.answer.await_args_list[-1].args[0].lower()), (
        f"11.1 не-админ: доступ запрещён: {query.answer.await_args_list}"
    )
    assert S.get_balance(_bb_target_id) == _bal_before, "11.2 не-админ: баланс не изменился"

    # 11.3: админ жмёт "Наградить" -> баланс +BUG_BOUNTY_REWARD, уведомление юзеру,
    # клавиатура заменена на "Награждено"
    _admin_id = 9603
    S.ADMIN_IDS.append(_admin_id)
    update, context, query = make_update_context(f"reward_bug_{_bb_target_id}", user_id=_admin_id)
    query.edit_message_reply_markup = AsyncMock()
    asyncio.run(S.button_handler(update, context))
    assert S.get_balance(_bb_target_id) == _bal_before + S.BUG_BOUNTY_REWARD, (
        f"11.3 админ: баланс увеличен на BUG_BOUNTY_REWARD: before={_bal_before} after={S.get_balance(_bb_target_id)}"
    )
    notify_calls = [c for c in context.bot.send_message.await_args_list if c.kwargs.get("chat_id") == _bb_target_id]
    assert bool(notify_calls) and "🎉" in notify_calls[-1].kwargs.get("text", ""), (
        f"11.4 админ: юзер получил уведомление о награде: {notify_calls}"
    )
    assert query.edit_message_reply_markup.await_args_list != [], (
        f"11.5 админ: клавиатура заменена на 'Награждено': {query.edit_message_reply_markup.await_args_list}"
    )

    S.ADMIN_IDS[:] = _orig_admin_ids

    # 11.6: bug_bounty_command выставляет waiting_for_bug_report и шлёт инструкцию
    update, context, message = make_text_update("/bugbounty", user_id=9604)
    asyncio.run(S.bug_bounty_command(update, context))
    st11 = context.user_data.get("state")
    assert isinstance(st11, S.UserState) and st11.waiting_for_bug_report is True, (
        "11.6 bug_bounty_command взводит waiting_for_bug_report"
    )
    sent11 = [c.args[0] for c in message.reply_text.await_args_list]
    assert any(str(S.BUG_BOUNTY_REWARD) in t and "🍇" in t for t in sent11), (
        f"11.7 bug_bounty_command упоминает награду в тексте: {sent11}"
    )

    # 11.8: текст после /bugbounty -> репорт уходит админам с bug_bounty_admin_kb
    _orig_admin_ids2 = list(S.ADMIN_IDS)
    S.ADMIN_IDS[:] = [9605]
    update, context, message = make_text_update("кнопка X не открывается", user_id=9606, state=st11)
    update.effective_user.full_name = "Bug Finder"
    context.bot.send_message = AsyncMock()
    asyncio.run(S.handle_text(update, context))
    assert (context.bot.send_message.await_args_list != []
            and "Наградить" in str(context.bot.send_message.await_args_list[-1].kwargs.get("reply_markup"))), (
        f"11.9 репорт улетел админу с кнопкой 'Наградить': {context.bot.send_message.await_args_list}"
    )
    assert st11.waiting_for_bug_report is False, "11.10 waiting_for_bug_report сброшен после отправки"
    assert st11.pending_report_kind == "bug", (
        f"11.11 текст репорта выставляет pending_report_kind='bug' (для скриншота вторым сообщением): {st11.pending_report_kind}"
    )
    S.ADMIN_IDS[:] = _orig_admin_ids2

    # 11.12: живой баг 2026-07-19 — скриншот вторым сообщением после текста
    # репорта раньше тихо утекал в обычные references генерации вместо репорта.
    _orig_admin_ids3 = list(S.ADMIN_IDS)
    S.ADMIN_IDS[:] = [9607]
    st11b = S.UserState(pending_report_kind="bug", pending_report_kind_at=time.time())
    photo_message = types.SimpleNamespace(
        photo=[types.SimpleNamespace(file_id="ph1")],
        caption=None, media_group_id=None, reply_text=AsyncMock(),
    )
    update = types.SimpleNamespace(
        message=photo_message,
        effective_user=types.SimpleNamespace(id=9608, username="test"),
        effective_chat=types.SimpleNamespace(id=9608),
        effective_message=photo_message,
    )
    context = types.SimpleNamespace(user_data={"state": st11b}, application=None, bot=AsyncMock())
    asyncio.run(S.handle_photo(update, context))
    assert st11b.references == [], f"11.12 скриншот к репорту НЕ попадает в references генерации: {st11b.references}"
    assert (context.bot.send_photo.await_args_list != []
            and context.bot.send_photo.await_args_list[-1].kwargs.get("photo") == "ph1"), (
        f"11.13 скриншот к репорту пересылается админу через send_photo: {context.bot.send_photo.await_args_list}"
    )
    assert st11b.pending_report_kind == "", "11.14 pending_report_kind сброшен после пересылки скриншота"
    photo_texts = [c.args[0] for c in photo_message.reply_text.await_args_list]
    assert any("скриншот добавлен" in t.lower() for t in photo_texts), (
        f"11.15 юзер получил подтверждение 'скриншот добавлен': {photo_texts}"
    )
    S.ADMIN_IDS[:] = _orig_admin_ids3

    # 11.16: TTL истёк -> фото уходит по обычному пути (в references), не как скриншот
    st11c = S.UserState(pending_report_kind="bug",
                         pending_report_kind_at=time.time() - S.PENDING_REPORT_SCREENSHOT_TTL_SECONDS - 10)
    photo_message2 = types.SimpleNamespace(
        photo=[types.SimpleNamespace(file_id="ph2")],
        caption=None, media_group_id=None, reply_text=AsyncMock(),
    )
    update = types.SimpleNamespace(
        message=photo_message2,
        effective_user=types.SimpleNamespace(id=9609, username="test"),
        effective_chat=types.SimpleNamespace(id=9609),
        effective_message=photo_message2,
    )
    context = types.SimpleNamespace(user_data={"state": st11c}, application=None, bot=AsyncMock())
    context.bot.get_file = AsyncMock(return_value=types.SimpleNamespace(
        download_to_memory=AsyncMock(side_effect=lambda out: out.write(base64.b64decode(ok_png_b64)))
    ))
    asyncio.run(S.handle_photo(update, context))
    assert len(st11c.references) == 1, (
        f"11.17 TTL истёк -> pending_report_kind не мешает обычной загрузке фото: {st11c.references}"
    )

    # 11.18: живой баг 2026-07-19 (второй за день) — текст+фото ОДНИМ сообщением
    # (caption) во время ожидания репорта раньше уходило как обычный промт+реф
    _orig_admin_ids4 = list(S.ADMIN_IDS)
    S.ADMIN_IDS[:] = [9610]
    st11d = S.UserState(waiting_for_bug_report=True)
    photo_message3 = types.SimpleNamespace(
        photo=[types.SimpleNamespace(file_id="ph3")],
        caption="кнопка X не открывается", media_group_id=None, reply_text=AsyncMock(),
    )
    update = types.SimpleNamespace(
        message=photo_message3,
        effective_user=types.SimpleNamespace(id=9611, username="test", full_name="Bug Finder"),
        effective_chat=types.SimpleNamespace(id=9611),
        effective_message=photo_message3,
    )
    context = types.SimpleNamespace(user_data={"state": st11d}, application=None, bot=AsyncMock())
    asyncio.run(S.handle_photo(update, context))
    assert st11d.prompt == "", f"11.18 текст+фото одним сообщением НЕ становится обычным промтом: {st11d.prompt}"
    assert st11d.references == [], f"11.19 текст+фото одним сообщением НЕ попадает в references: {st11d.references}"
    assert st11d.waiting_for_bug_report is False, "11.20 waiting_for_bug_report сброшен"
    sent_calls = context.bot.send_message.await_args_list
    assert (sent_calls != []
            and "кнопка X не открывается" in sent_calls[-1].kwargs.get("text", "")
            and "Наградить" in str(sent_calls[-1].kwargs.get("reply_markup"))), (
        f"11.21 репорт (текст) ушёл админу с кнопкой 'Наградить': {sent_calls}"
    )
    photo_calls = context.bot.send_photo.await_args_list
    assert photo_calls != [] and photo_calls[-1].kwargs.get("photo") == "ph3", (
        f"11.22 фото из этого же сообщения тоже переслано админу: {photo_calls}"
    )
    S.ADMIN_IDS[:] = _orig_admin_ids4
