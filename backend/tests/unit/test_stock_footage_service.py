import pytest

from src.services import stock_footage_service as stock


def make_video(video_id: int, name: str = "Someone"):
    return {
        "id": video_id,
        "width": 1080,
        "height": 1920,
        "duration": 12,
        "image": f"https://example.test/{video_id}.jpg",
        "user": {"name": name, "url": f"https://example.test/u/{name}"},
        "video_files": [
            {"quality": "sd", "width": 540, "height": 960, "link": f"sd-{video_id}"},
            {"quality": "hd", "width": 1080, "height": 1920, "link": f"hd-{video_id}"},
        ],
    }


@pytest.fixture
def fake_search(monkeypatch):
    """Replace the Pexels client with a scripted keyword -> results map."""
    calls = []
    results_by_keyword: dict = {}

    async def _search(keyword, orientation="portrait", size="medium", per_page=5):
        calls.append(keyword)
        value = results_by_keyword.get(keyword, [])
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(stock, "search_broll_videos", _search)
    monkeypatch.setattr(stock, "is_configured", lambda: True)
    return results_by_keyword, calls


@pytest.mark.asyncio
async def test_summarises_a_result_for_the_review_screen(fake_search):
    results, _ = fake_search
    results["office"] = [make_video(1, "Ada")]

    found = await stock.find_for_keywords(["office"])

    assert found == [
        {
            "id": 1,
            "width": 1080,
            "height": 1920,
            "duration": 12,
            "thumbnail": "https://example.test/1.jpg",
            "preview_url": "sd-1",
            "download_url": "hd-1",
            "author": "Ada",
            "author_url": "https://example.test/u/Ada",
            "source": "pexels",
        }
    ]


@pytest.mark.asyncio
async def test_later_keywords_only_fill_remaining_slots(fake_search):
    results, calls = fake_search
    results["first"] = [make_video(1), make_video(2)]
    results["second"] = [make_video(3), make_video(4)]

    found = await stock.find_for_keywords(["first", "second"], limit=3)

    # The most specific keyword comes first and contributes first.
    assert [item["id"] for item in found] == [1, 2, 3]
    assert calls == ["first", "second"]


@pytest.mark.asyncio
async def test_stops_searching_once_the_limit_is_reached(fake_search):
    results, calls = fake_search
    results["first"] = [make_video(1), make_video(2)]
    results["second"] = [make_video(3)]

    await stock.find_for_keywords(["first", "second"], limit=2)

    # No point paying for a second request when the list is already full.
    assert calls == ["first"]


@pytest.mark.asyncio
async def test_drops_the_same_video_found_by_two_keywords(fake_search):
    results, _ = fake_search
    results["a"] = [make_video(7)]
    results["b"] = [make_video(7), make_video(8)]

    found = await stock.find_for_keywords(["a", "b"], limit=4)

    assert [item["id"] for item in found] == [7, 8]


@pytest.mark.asyncio
async def test_a_failing_keyword_does_not_sink_the_others(fake_search):
    results, _ = fake_search
    results["broken"] = RuntimeError("pexels down")
    results["fine"] = [make_video(9)]

    found = await stock.find_for_keywords(["broken", "fine"], limit=4)

    assert [item["id"] for item in found] == [9]


@pytest.mark.asyncio
async def test_blank_keywords_are_skipped(fake_search):
    results, calls = fake_search
    results["real"] = [make_video(1)]

    await stock.find_for_keywords(["", "   ", "real"], limit=4)

    assert calls == ["real"]


@pytest.mark.asyncio
async def test_scenes_keep_their_order_and_preselect_the_first_candidate(fake_search):
    results, _ = fake_search
    results["one"] = [make_video(11), make_video(12)]
    results["two"] = [make_video(21)]

    scenes = [
        {"order": 1, "stock_keywords": ["one"]},
        {"order": 2, "stock_keywords": ["two"]},
    ]
    found = await stock.find_for_scenes(scenes)

    assert [scene["order"] for scene in found] == [1, 2]
    assert found[0]["selected_id"] == 11
    assert found[1]["selected_id"] == 21


@pytest.mark.asyncio
async def test_a_scene_with_no_results_is_reported_not_dropped(fake_search):
    results, _ = fake_search
    results["hit"] = [make_video(1)]

    scenes = [
        {"order": 1, "stock_keywords": ["hit"]},
        {"order": 2, "stock_keywords": ["miss"]},
    ]
    found = await stock.find_for_scenes(scenes)

    # The empty scene still comes back so the UI can ask for new keywords.
    assert len(found) == 2
    assert found[1]["candidates"] == []
    assert found[1]["selected_id"] is None
    assert stock.missing_scene_orders(found) == [2]


@pytest.mark.asyncio
async def test_refuses_clearly_when_no_provider_is_configured(monkeypatch):
    monkeypatch.setattr(stock, "is_configured", lambda: False)

    with pytest.raises(stock.StockFootageUnavailable, match="PEXELS_API_KEY"):
        await stock.find_for_scenes([{"order": 1, "stock_keywords": ["x"]}])
