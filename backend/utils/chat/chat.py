import database.chat as chat_db


def clear_user_chat_message(uid: str):
    err = chat_db.clear_chat(uid)
    return err
