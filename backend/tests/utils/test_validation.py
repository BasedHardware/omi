import pytest
from utils.validation import validate_email

def test_validate_email():
    """Test email validation"""
    # Valid emails
    assert validate_email("test@example.com") == True
    assert validate_email("user.name+tag@domain.co.uk") == True
    assert validate_email("x@y.z") == True
    
    # Invalid emails
    assert validate_email("") == False
    assert validate_email("not_an_email") == False
    assert validate_email("missing@domain") == False
    assert validate_email("@no_user.com") == False
    assert validate_email("spaces in@email.com") == False
    assert validate_email("missing.domain@") == False
    assert validate_email("two@@at.com") == False
    assert validate_email(None) == False
    assert validate_email(123) == False  # Non-string input