"""Regression test: a Hume job-submit success response missing job_id must not raise.

utils.other.hume.HumeJobResponseModel.from_dict is called on the success (HTTP 200) path
with resp.json(). It read data["job_id"] with a required-key subscript, so a 200 response
that omits job_id raised KeyError out of request_user_expression_mersurement, even though
every error status is already turned into an error dict. HumeJobResponseModel.__init__ types
id as Optional[str], so from_dict now reads job_id defensively and leaves id None when absent.
"""

from utils.other.hume import HumeJobResponseModel


def test_from_dict_with_job_id():
    model = HumeJobResponseModel.from_dict({"job_id": "abc123"})
    assert model.id == "abc123"


def test_from_dict_missing_job_id_does_not_raise():
    model = HumeJobResponseModel.from_dict({})
    assert model.id is None


def test_from_dict_ignores_extra_keys():
    model = HumeJobResponseModel.from_dict({"job_id": "j", "status": "queued"})
    assert model.id == "j"
