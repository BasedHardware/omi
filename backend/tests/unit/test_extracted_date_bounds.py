"""Contract tests for utils.llm.temporal.normalize_extracted_dates.

The conversation metadata-extraction paths in utils/llm/chat.py turn model-extracted dates into
the ``dates`` search filters (``add_filter_category_item(uid, 'dates', ...)`` plus the conversation
vector metadata). They used to bound those dates with a hardcoded ``if date.year > 2025: continue``
and a prompt line saying "Do not include dates greater than 2025". Once 2025 passed, that stopped
rejecting implausible dates and started discarding every real one: external-integration
conversations (message/text sources) recorded no dates at all, and the prompt actively steered the
model away from the correct year.

The bound is now relative to the content's own date. These tests lock that: a present-day date
survives, a far-future one is still rejected, a partial date the model sometimes emits (e.g.
``'2027-02'``, seen in prod logs) is dropped without raising, and an unusable reference date never
discards the whole set.
"""

from utils.llm.temporal import MAX_EXTRACTED_DATE_LOOKAHEAD_DAYS, normalize_extracted_dates


class TestPresentDayDatesSurvive:
    def test_date_in_the_reference_year_is_kept(self):
        # The regression: with the hardcoded 2025 cutoff this returned [].
        assert normalize_extracted_dates(['2026-07-29'], '2026-07-29') == ['2026-07-29']

    def test_next_year_within_the_lookahead_is_kept(self):
        assert normalize_extracted_dates(['2027-01-15'], '2026-07-29') == ['2027-01-15']

    def test_real_far_ahead_plan_is_kept(self):
        # "the wedding is in about 18 months" must not be discarded as a hallucination.
        assert normalize_extracted_dates(['2028-01-15'], '2026-07-29') == ['2028-01-15']

    def test_past_dates_are_kept(self):
        assert normalize_extracted_dates(['2019-03-04'], '2026-07-29') == ['2019-03-04']

    def test_reference_year_rolls_forward_without_a_code_change(self):
        assert normalize_extracted_dates(['2031-05-02'], '2031-05-02') == ['2031-05-02']


class TestImplausibleDatesRejected:
    def test_date_beyond_the_lookahead_is_dropped(self):
        assert normalize_extracted_dates(['2030-01-01'], '2026-07-29') == []

    def test_lookahead_boundary_is_inclusive(self):
        # 2026-07-29 + 731 days = 2028-07-29.
        assert MAX_EXTRACTED_DATE_LOOKAHEAD_DAYS == 731
        assert normalize_extracted_dates(['2028-07-29'], '2026-07-29') == ['2028-07-29']
        assert normalize_extracted_dates(['2028-07-30'], '2026-07-29') == []


class TestUnparseableInput:
    def test_partial_date_is_dropped_without_raising(self):
        assert normalize_extracted_dates(['2027-02'], '2026-07-29') == []

    def test_free_text_is_dropped_without_raising(self):
        assert normalize_extracted_dates(['next tuesday', ''], '2026-07-29') == []

    def test_none_dates_returns_empty(self):
        assert normalize_extracted_dates(None, '2026-07-29') == []

    def test_good_dates_survive_alongside_bad_ones(self):
        assert normalize_extracted_dates(['2027-02', '2026-08-01'], '2026-07-29') == ['2026-08-01']


class TestUnusableReferenceDate:
    def test_empty_reference_keeps_parseable_dates(self):
        # A missing reference must not silently discard the whole set — that is the failure mode
        # this helper exists to prevent.
        assert normalize_extracted_dates(['2026-08-01'], '') == ['2026-08-01']

    def test_malformed_reference_keeps_parseable_dates(self):
        assert normalize_extracted_dates(['2026-08-01'], 'not-a-date') == ['2026-08-01']
