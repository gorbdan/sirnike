# -*- coding: utf-8 -*-
"""Блок 20: FREE_GENERATIONS_PER_DAY=0 не раздаёт халяву (прод-баг 2026-08-06).

try_use_free_generation с max_per_day=0 (халява выключена, прод-дефолт)
выдавала бесплатный слот через ветку «новый день»: условие
free_used_date != today (у новичков NULL) срабатывало без сверки с лимитом.
Итог — КАЖДЫЙ юзер получал одну бесплатную фото/аватар-генерацию в день,
навсегда, START_BONUS и оплата не требовались. Списание не происходило ни разу,
пока юзер укладывался в 1 генерацию в день.
"""
from test_helpers import S  # noqa: F401 — сетап env/DATA_DIR до импорта db

import db

db.init_db()


def _make_user(user_id):
    # Чистый новичок: free_used_date IS NULL, free_used_count = 0
    db.delete_user_for_test(user_id)
    db.create_user_if_not_exists(user_id, "freegen_test", start_bonus=5)


def test_block_20a_limit_zero_new_user_gets_no_free_slot():
    uid = 920001
    _make_user(uid)
    assert db.try_use_free_generation(uid, 0) is False, (
        "20a.1 лимит 0: новичок (free_used_date=NULL) НЕ должен получать бесплатный слот"
    )
    assert db.try_use_free_generation(uid, 0) is False, (
        "20a.2 лимит 0: повторный вызов тоже False"
    )


def test_block_20b_limit_zero_stale_date_gets_no_free_slot():
    # Юзер, у которого free_used_date «вчерашняя» — вторая половина той же дыры
    uid = 920002
    _make_user(uid)
    with db.get_conn() as conn:
        conn.execute(
            "UPDATE users SET free_used_date = '2026-01-01', free_used_count = 1 WHERE user_id = ?",
            (uid,),
        )
        conn.commit()
    assert db.try_use_free_generation(uid, 0) is False, (
        "20b.1 лимит 0: юзер со старой датой НЕ должен получать слот в новый день"
    )


def test_block_20c_negative_limit_treated_as_disabled():
    uid = 920003
    _make_user(uid)
    assert db.try_use_free_generation(uid, -1) is False, (
        "20c.1 отрицательный лимит = халява выключена"
    )


def test_block_20d_positive_limit_still_works():
    # Гейт не должен сломать легитимную халяву, когда её включат
    uid = 920004
    _make_user(uid)
    assert db.try_use_free_generation(uid, 2) is True, (
        "20d.1 лимит 2: первый слот выдан (ветка «новый день»)"
    )
    assert db.try_use_free_generation(uid, 2) is True, (
        "20d.2 лимит 2: второй слот выдан (инкремент в пределах лимита)"
    )
    assert db.try_use_free_generation(uid, 2) is False, (
        "20d.3 лимит 2: третий слот НЕ выдан"
    )
    db.restore_free_generation(uid)
    assert db.try_use_free_generation(uid, 2) is True, (
        "20d.4 после restore слот снова доступен"
    )
