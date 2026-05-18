"""Schema dataclass tests."""
from grail.schemas import Community, CommunityReport, Entity, Relationship, TextUnit


def test_entity_from_dict_roundtrip():
    d = {
        "id": "e-1",
        "title": "Alice",
        "type": "person",
        "description": "Researcher",
        "degree": 4,
        "community": ["1", "2"],
    }
    ent = Entity.from_dict(d)
    assert ent.title == "Alice"
    assert ent.type == "person"
    assert ent.rank == 4
    assert ent.community_ids == ["1", "2"]


def test_relationship_default_weight():
    r = Relationship.from_dict({"id": "r-1", "source": "A", "target": "B"})
    assert r.weight == 1.0


def test_text_unit_required_fields():
    tu = TextUnit.from_dict({"id": "t-1", "text": "hello"})
    assert tu.text == "hello"
    assert tu.entity_ids is None


def test_community_and_report_named_titles():
    c = Community.from_dict({"id": "c", "title": "T", "level": "0"})
    cr = CommunityReport.from_dict(
        {
            "id": "cr",
            "title": "Report",
            "community_id": "c",
            "summary": "s",
            "full_content": "f",
            "rank": 7,
        }
    )
    assert c.level == "0"
    assert cr.rank == 7
