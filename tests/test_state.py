from immich_tg_bot.state import State


async def test_records_do_not_cross_platforms_for_same_user_id():
    state = State()
    await state.create_ingest_record(42, "chat", "telegram-message", platform="telegram")
    await state.create_ingest_record(42, "chat", "discord-message", platform="discord")

    telegram = await state.recent_ingest_records(42, platform="telegram")
    discord = await state.recent_ingest_records(42, platform="discord")
    assert [record.message_id for record in telegram] == ["telegram-message"]
    assert [record.message_id for record in discord] == ["discord-message"]


async def test_records_are_limited_to_owner():
    state = State()
    for number in range(6):
        record = await state.create_ingest_record(42, "20", str(number))
        await state.finish_ingest_record(record, "completed", 1, 2, 3, 0, "")
    failed = await state.create_ingest_record(99, "20", "secret")
    await state.finish_ingest_record(failed, "failed", 0, 0, 0, 1, "bad.jpg: upload: failed")
    records = await state.recent_ingest_records(42)
    assert [record.message_id for record in records] == ["5", "4", "3", "2", "1"]
    assert (records[0].status, records[0].uploaded, records[0].duplicates, records[0].skipped) == (
        "completed",
        1,
        2,
        3,
    )
    other = await state.recent_ingest_records(99)
    assert other[0].status == "failed"
    assert other[0].details == "bad.jpg: upload: failed"
    assert await state.recent_ingest_records(100) == []


async def test_old_active_import_can_finish_after_five_newer_requests():
    state = State()
    active = await state.create_ingest_record(42, "20", "active")
    await state.start_ingest_record(active)
    for number in range(5):
        await state.create_ingest_record(42, "20", str(number))

    await state.finish_ingest_record(active, "completed", 1, 0, 0, 0, "")
    assert [record.message_id for record in await state.recent_ingest_records(42)] == [
        "4",
        "3",
        "2",
        "1",
        "0",
    ]
