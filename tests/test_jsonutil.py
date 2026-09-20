from edgar_mcp.jsonutil import get_field, jsonable


def test_jsonable_round_trip_types():
    assert jsonable(None) is None
    assert jsonable(3) == 3
    assert jsonable({"a": 1}) == {"a": 1}
    assert jsonable((1, 2)) == [1, 2]


def test_get_field_dict_and_object():
    class Obj:
        ticker = "JPM"

    assert get_field({"ticker": "JPM"}, "ticker") == "JPM"
    assert get_field(Obj(), "ticker") == "JPM"
    assert get_field({}, "missing", default="x") == "x"
