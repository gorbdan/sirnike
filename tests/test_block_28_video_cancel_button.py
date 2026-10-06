# -*- coding: utf-8 -*-
"""Блок 28: «❌ Остановить» на статусе видео-генерации (живой запрос Ани
2026-10-06). run_seedance исполняется личной asyncio.Task на юзера
(active_video_tasks) — кнопка вызывает task.cancel(), CancelledError
долетает до except BaseException внутри run_seedance, где уже есть рефанд +
явное сообщение «остановлена» вместо пугающего «технический сбой».

Кнопки нет у фото (queue_worker последовательный и общий на всех юзеров —
отменить одного без риска уронить чужую генерацию нельзя без отдельного
рефакторинга очереди) — см. комментарий у active_video_tasks в SirNike.py."""
import asyncio

from test_helpers import S, make_update_context


def test_block_28a_cancel_with_no_active_task_shows_alert():
    # button_handler сам безусловно зовёт query.answer() один раз ДО диспетчера
    # (гасит спиннер) — наш хендлер зовёт его ВТОРОЙ раз с текстом/алертом,
    # тот же established-паттерн, что у _cb_toggle_avatar_skip и соседей.
    # Проверяем ПОСЛЕДНИЙ вызов, не общее количество.
    assert 999999901 not in S.active_video_tasks, "28a.0 чистое состояние перед тестом"
    update, context, query = make_update_context("video_cancel_gen", user_id=999999901)
    asyncio.run(S.button_handler(update, context))
    assert query.answer.await_count == 2, f"28a.1 answer() вызван дважды (button_handler + хендлер): {query.answer.await_count}"
    args, kwargs = query.answer.await_args
    assert kwargs.get("show_alert") is True, f"28a.2 алерт, не тихий тост: {kwargs}"
    assert "заверш" in args[0].lower(), f"28a.3 текст объясняет, что нечего останавливать: {args}"


def test_block_28b_cancel_with_active_task_calls_cancel():
    user_id = 999999902

    async def _never_ending():
        await asyncio.sleep(3600)

    async def _run():
        task = asyncio.get_event_loop().create_task(_never_ending())
        S.active_video_tasks[user_id] = task
        try:
            update, context, query = make_update_context("video_cancel_gen", user_id=user_id)
            await S.button_handler(update, context)
            # cancel() только ЗАПРАШИВАЕТ отмену — дождёмся, чтобы она применилась.
            try:
                await task
            except asyncio.CancelledError:
                pass
            assert task.cancelled(), "28b.2 задача реально отменена"
            assert query.answer.await_count == 2, f"28b.3 answer() вызван дважды: {query.answer.await_count}"
            args, _ = query.answer.await_args
            assert "останавлива" in args[0].lower(), f"28b.4 подтверждение юзеру: {args}"
        finally:
            S.active_video_tasks.pop(user_id, None)

    asyncio.run(_run())


def test_block_28c_cancel_with_already_done_task_shows_alert():
    user_id = 999999903

    async def _instant():
        return "done"

    async def _run():
        task = asyncio.get_event_loop().create_task(_instant())
        await task  # уже завершена к моменту клика
        S.active_video_tasks[user_id] = task
        try:
            update, context, query = make_update_context("video_cancel_gen", user_id=user_id)
            await S.button_handler(update, context)
            assert query.answer.await_count == 2, f"28c.1 answer() вызван дважды: {query.answer.await_count}"
            _, kwargs = query.answer.await_args
            assert kwargs.get("show_alert") is True, "28c.2 завершённая задача -> алерт, не тихая отмена"
        finally:
            S.active_video_tasks.pop(user_id, None)

    asyncio.run(_run())


def test_block_28d_gen_progress_kb_with_extra_rows():
    kb_plain = S.gen_progress_kb(1, "pid", "video")
    assert len(kb_plain.inline_keyboard) == 1, f"28d.1 без extra_rows — одна строка: {kb_plain.inline_keyboard}"

    cancel_row = [S.InlineKeyboardButton("❌ Остановить", callback_data="video_cancel_gen")]
    kb_with_cancel = S.gen_progress_kb(1, "pid", "video", extra_rows=[cancel_row])
    assert len(kb_with_cancel.inline_keyboard) == 2, f"28d.2 с extra_rows — две строки: {kb_with_cancel.inline_keyboard}"
    assert kb_with_cancel.inline_keyboard[1][0].callback_data == "video_cancel_gen", (
        f"28d.3 вторая строка — кнопка отмены: {kb_with_cancel.inline_keyboard}"
    )
    # Первая строка (ссылка на прогресс) не пострадала от добавления второй.
    assert kb_with_cancel.inline_keyboard[0][0].text == kb_plain.inline_keyboard[0][0].text, (
        "28d.4 исходная кнопка «Смотреть прогресс» не изменилась"
    )
