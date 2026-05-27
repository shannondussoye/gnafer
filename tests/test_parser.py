"""Tests for LLM verifier response parsing."""

import pytest

from src.llm_verifier import LLMVerifier


@pytest.fixture
def verifier():
    return LLMVerifier(model="test", host="http://localhost:11434")


def test_parse_response_true(verifier):
    assert verifier._parse_response('{"match": true}') is True


def test_parse_response_false(verifier):
    assert verifier._parse_response('{"match": false}') is False


def test_parse_response_invalid_json(verifier):
    assert verifier._parse_response("not json") is False


def test_parse_response_missing_key(verifier):
    assert verifier._parse_response('{"result": true}') is False


def test_build_prompt(verifier):
    prompt = verifier._build_prompt("14 Smith St, Sydney", "14 SMITH ST, SYDNEY NSW 2000")
    assert "INPUT:" in prompt
    assert "CANDIDATE:" in prompt
    assert "14 Smith St" in prompt
