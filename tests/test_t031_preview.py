"""T-031 covers authenticated preview routes too; /about alone is exempt."""
import pytest

from test_field_neutral_labels import FIELD, assert_neutral, client, neutral_world  # noqa: F401


@pytest.mark.parametrize("who,role", FIELD)
def test_tabler_preview_field_access_is_neutral(db, neutral_world, who, role):
    people, _, _, _ = neutral_world
    with client(people[who], role) as c:
        response = c.get("/stats/tabler-preview", follow_redirects=False)
    # Either deny this design preview or apply the same field label contract.
    # The test does not choose a new business access rule.
    assert response.status_code in (200, 403, 404)
    assert_neutral(response.text, "/stats/tabler-preview HTML")
