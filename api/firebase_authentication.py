import os
from functools import lru_cache

import firebase_admin
from firebase_admin import auth, credentials


@lru_cache(maxsize=1)
def initialise_firebase():
#To fill

def verify_firebase_token(id_token: str) -> dict:
#To fill


def get_current_user(
    authorization: str = Header(..., alias="Authorization")
) -> dict:
#To fill