"""Only whitelisted numeric/bounded fields may leave the offline log audit."""

from scripts.audit_smart_merge_wallclock import summarize


def test_content_free_summary_drops_owner_ids_and_arbitrary_fields():
    result = summarize(
        [
            {
                'textPayload': 'event=smart_merge_wallclock_shadow would=merge reason=jev_same p_same=0.36 gap_wall_s=180 uid=private-owner extra=private-value'
            },
            {
                'textPayload': 'event=smart_merge_wallclock_shadow would=kept reason=jev_different p_same=0.1 gap_wall_s=240'
            },
            {
                'textPayload': 'event=smart_merge_wallclock_shadow would=skip reason=jev_unavailable p_same=None gap_wall_s=150'
            },
            {'textPayload': 'unrelated private-value'},
            {'textPayload': 'event=smart_merge_wallclock_shadow would=private-value reason=private-value'},
        ]
    )
    assert result['decisions'] == {
        'merge:jev_same': 1,
        'kept:jev_different': 1,
        'skip:jev_unavailable': 1,
        'unrecognized': 1,
    }
    assert result['score_count'] == 2 and result['scores_near_cutoff_030_040'] == 1
    assert result['wall_gap_min_seconds'] == 150 and result['wall_gap_max_seconds'] == 240
    assert 'private-' not in str(result)


def test_nonfinite_values_are_omitted():
    result = summarize(
        [{'textPayload': 'event=smart_merge_wallclock_shadow would=merge reason=jev_same p_same=nan gap_wall_s=inf'}]
    )
    assert result['score_count'] == result['wall_gap_count'] == 0
