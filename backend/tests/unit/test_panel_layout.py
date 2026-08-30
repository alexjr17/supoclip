import pytest

from src.panel_layout import (
    MAX_PEOPLE,
    MIN_PEOPLE,
    build_panel_filtergraph,
    cluster_people,
    is_suitable,
    neighbour_gaps,
    panel_geometry,
    tile_grid,
)


def test_tiles_are_portrait_not_landscape_bands():
    tile_w, tile_h = tile_grid(1080, 1920)

    # 540x960: taller than wide, which is the shape a person occupies. Three
    # horizontal bands would be landscape and pull in the neighbours.
    assert (tile_w, tile_h) == (540, 960)
    assert tile_h > tile_w


def test_neighbour_gaps_measure_the_closest_other_person():
    gaps = neighbour_gaps([(100.0, 500.0), (400.0, 500.0), (1000.0, 500.0)])

    assert gaps == [300.0, 300.0, 600.0]


def test_a_lone_person_has_no_neighbour_gap():
    assert neighbour_gaps([(100.0, 500.0)]) == [None]


def test_crop_is_clamped_to_the_space_a_person_owns():
    tile_w, tile_h = tile_grid(1080, 1920)
    wide, _, _, _ = panel_geometry(1920, 1080, tile_w, tile_h, (960.0, 400.0))
    clamped, _, _, _ = panel_geometry(
        1920, 1080, tile_w, tile_h, (960.0, 400.0), neighbour_gap=300.0
    )

    # Without the clamp the crop is as wide as the tile aspect allows; with a
    # neighbour 300px away it shrinks below that, leaving a margin.
    assert clamped < wide
    assert clamped <= int(300 * 0.9)


def test_crop_dimensions_are_even():
    tile_w, tile_h = tile_grid(1080, 1920)
    for gap in (None, 301.0, 457.0):
        crop_w, crop_h, x, y = panel_geometry(
            1920, 1080, tile_w, tile_h, (960.0, 400.0), neighbour_gap=gap
        )
        assert crop_w % 2 == 0 and crop_h % 2 == 0
        assert x % 2 == 0 and y % 2 == 0


def test_crop_stays_inside_the_frame_for_an_edge_person():
    tile_w, tile_h = tile_grid(1080, 1920)
    crop_w, crop_h, x, y = panel_geometry(1920, 1080, tile_w, tile_h, (30.0, 1050.0))

    assert x >= 0 and y >= 0
    assert x + crop_w <= 1920
    assert y + crop_h <= 1080


def test_four_people_use_four_tiles():
    centers = [(200.0, 500.0), (700.0, 500.0), (1200.0, 500.0), (1700.0, 500.0)]
    graph = build_panel_filtergraph(1920, 1080, centers)

    assert "[0:v]split=4" in graph
    assert "hstack=inputs=2" in graph
    assert "vstack=inputs=2" in graph
    assert graph.endswith("[v]")


def test_three_people_fill_the_fourth_tile_with_the_wide_shot():
    centers = [(300.0, 500.0), (960.0, 500.0), (1600.0, 500.0)]
    graph = build_panel_filtergraph(1920, 1080, centers)

    # A fourth stream is split off and padded rather than cropped, so the room
    # shot loses nothing.
    assert "[0:v]split=4" in graph
    assert "[s3]scale=540:-2" in graph
    assert "pad=540:960" in graph


def test_filtergraph_appends_subtitles_last():
    centers = [(300.0, 500.0), (960.0, 500.0), (1600.0, 500.0)]
    graph = build_panel_filtergraph(1920, 1080, centers, subtitles_filter="subtitles=x.ass")

    assert graph.endswith(",subtitles=x.ass[v]")


def test_filtergraph_rejects_the_wrong_headcount():
    with pytest.raises(ValueError):
        build_panel_filtergraph(1920, 1080, [(100.0, 500.0), (900.0, 500.0)])
    with pytest.raises(ValueError):
        build_panel_filtergraph(1920, 1080, [(i * 300.0, 500.0) for i in range(5)])


def test_suitability_needs_a_landscape_source_and_a_crowd():
    assert is_suitable(1920, 1080, 3) is True
    assert is_suitable(1920, 1080, 4) is True
    assert is_suitable(1920, 1080, 2) is False
    assert is_suitable(1080, 1920, 3) is False


def test_clustering_collapses_repeated_detections_of_one_person():
    # The same three people detected across several frames, with jitter.
    detections = [
        (300.0, 500.0), (305.0, 502.0), (298.0, 498.0),
        (960.0, 510.0), (955.0, 508.0),
        (1600.0, 495.0), (1605.0, 497.0),
    ]
    people = cluster_people(detections, 1920)

    # Each person collapses to their cluster's median. For an even-sized
    # cluster that is the upper of the two middle values.
    assert len(people) == 3
    assert [round(x) for x, _ in people] == [300, 960, 1605]


def test_clustering_returns_people_left_to_right():
    detections = [(1600.0, 500.0), (300.0, 500.0), (960.0, 500.0)]
    people = cluster_people(detections, 1920)

    assert [x for x, _ in people] == sorted(x for x, _ in people)


def test_clustering_caps_at_the_grid_size():
    detections = [(i * 250.0, 500.0) for i in range(1, 8)]
    people = cluster_people(detections, 1920)

    assert len(people) <= MAX_PEOPLE


def test_clustering_handles_no_detections():
    assert cluster_people([], 1920) == []


def test_people_bounds_are_consistent():
    assert MIN_PEOPLE == 3 and MAX_PEOPLE == 4
