import pytest
from database.auth import create_user, get_user, delete_user, validate_token, update_user, get_user_from_uid, get_user_name
from unittest.mock import patch, MagicMock
from fastapi import HTTPException

@pytest.fixture
def mock_firestore():
    """Mock firestore with proper document references"""
    with patch('database._client._db', None):  # Reset singleton
        with patch('database._client.firestore.Client') as mock_client:
            # Create mock document
            mock_doc = MagicMock()
            mock_doc.exists = True
            mock_doc.to_dict.return_value = {
                "name": "Test User",
                "email": "test@example.com",
                "preferences": {"theme": "dark"}
            }
            
            # Create mock document reference
            mock_doc_ref = MagicMock()
            mock_doc_ref.get.return_value = mock_doc
            
            # Setup collection mock
            mock_collection = MagicMock()
            mock_collection.document.return_value = mock_doc_ref
            
            # Setup firestore mock
            mock_client_instance = mock_client.return_value
            mock_client_instance.collection.return_value = mock_collection
            
            yield mock_client_instance

@pytest.fixture
def mock_firebase_auth():
    """Mock firebase auth"""
    with patch('database.auth.auth') as mock:
        mock.verify_id_token.return_value = {
            "uid": "user123",
            "email": "test@example.com",
            "email_verified": True
        }
        mock.get_user.return_value = MagicMock(
            uid="user123",
            email="test@example.com",
            email_verified=True,
            display_name="Test User",
            phone_number=None,
            photo_url=None,
            disabled=False
        )
        yield mock

class TestUserCRUD:
    def test_create_user(self, mock_firestore):
        user_data = {
            "email": "test@example.com",
            "name": "Test User",
            "preferences": {"notifications": True}
        }
        mock_doc_ref = mock_firestore.collection().document()
        result = create_user("user123", user_data)
        
        mock_doc_ref.set.assert_called_once_with(user_data)
        assert result == "user123"

    def test_get_user(self, mock_firestore):
        mock_doc = mock_firestore.collection().document().get()
        mock_doc.exists = True
        mock_doc.to_dict.return_value = {
            "name": "Test User",
            "email": "test@example.com",
            "preferences": {"theme": "dark"}
        }
        
        user = get_user("user123")
        assert user["name"] == "Test User"
        assert user["preferences"]["theme"] == "dark"

    def test_get_nonexistent_user(self, mock_firestore):
        mock_doc = mock_firestore.collection().document().get()
        mock_doc.exists = False
        
        with pytest.raises(HTTPException) as exc:
            get_user("nonexistent")
        assert exc.value.status_code == 404
        assert "User not found" in str(exc.value.detail)

    def test_delete_user(self, mock_firestore):
        mock_doc_ref = mock_firestore.collection().document()
        delete_user("user123")
        mock_doc_ref.delete.assert_called_once()

    def test_update_user(self, mock_firestore):
        user_data = {
            "name": "Updated Name",
            "preferences": {"theme": "light"}
        }
        mock_doc_ref = mock_firestore.collection().document()
        
        update_user("user123", user_data)
        mock_doc_ref.update.assert_called_once_with(user_data)

class TestTokenValidation:
    def test_validate_valid_token(self, mock_firebase_auth):
        result = validate_token("valid_token")
        assert result == "user123"
        mock_firebase_auth.verify_id_token.assert_called_once_with("valid_token")

    def test_validate_invalid_token(self, mock_firebase_auth):
        mock_firebase_auth.verify_id_token.side_effect = Exception("Invalid token")
        
        with pytest.raises(HTTPException) as exc:
            validate_token("invalid_token")
        assert exc.value.status_code == 401
        assert "Invalid token" in str(exc.value.detail)

class TestUserInfo:
    def test_get_user_from_uid_success(self, mock_firebase_auth):
        result = get_user_from_uid("user123")
        assert result["uid"] == "user123"
        assert result["email"] == "test@example.com"
        assert result["email_verified"] is True

    def test_get_user_from_uid_nonexistent(self, mock_firebase_auth):
        mock_firebase_auth.get_user.side_effect = Exception("User not found")
        result = get_user_from_uid("nonexistent")
        assert result is None

    def test_get_user_name_success(self, mock_firebase_auth):
        with patch('database.auth.cache_user_name') as mock_cache:
            result = get_user_name("user123")
            assert result == "Test"  # First part of display_name
            mock_cache.assert_called_once()

    def test_get_user_name_default(self, mock_firebase_auth):
        mock_firebase_auth.get_user.return_value.display_name = None
        result = get_user_name("user123")
        assert result == "The User"