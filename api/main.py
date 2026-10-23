import uuid

from fastapi import Depends, FastAPI, HTTPException

from database import connection, initialise_database
from game import fresh, present, apply
from models import *


# Create the AI Archive API.
app = FastAPI(title="The AI Archive API")

GAMES = {}
REQUESTS = {}

def save_game(gid, state):
    GAMES[gid] = state

def load_game(gid):
    return GAMES.get(gid)

def save_request(rid, data):
    REQUESTS[rid] = data

def load_request(rid):
    return REQUESTS.get(rid)

def current_user():
    return {"uid": "dev-user"}

def owned_game(gid, user):
    state = load_game(gid)

    if state is None or state["owner"] != user["uid"]:
        raise HTTPException(status_code=404, detail="Game not found")

    return state

# Initialise persistent data and start background result processing.
@app.on_event("startup")
def startup():
    initialise_database()

# GET /health
# Confirm that the API and its required state service are available.
@app.get("/health")
def health():
    try:
        with connection() as c:
             c.execute("SELECT 1")
    except Exception:
        raise HTTPException(status_code=503, detail="Database unavailable")

    return {
        "status": "healthy",
        "database": "sqlite", 
        "authentication": "firebase"
    }
# GET /api/v1/authentication/me
# Return the identity of the authenticated user.
@app.get("/api/v1/authentication/me")
def me(user: dict = Depends(current_user)):
    return user


# POST /api/v1/games
# Create a new game owned by the authenticated user and return its initial state.
@app.post("/api/v1/games")
def create_game(user: dict = Depends(current_user)):
    gid = str(uuid.uuid4())
    state = fresh(user["uid"])
    save_game(gid, state)

    return {"game_id": gid, **present(state)}

# GET /api/v1/games/{gid}
# Return a game only when it exists and belongs to the authenticated user.
@app.get("/api/v1/games/{gid}")
def get_game(gid: str, user:dict = Depends(current_user)):
    state = owned_game(gid, user)

    return {"game_id": gid, **present(state)}

# POST /api/v1/games/{gid}/actions
# Accept a player command and create an asynchronous request.
# Return the existing request when the same request_id is submitted again.
@app.post("/api/v1/games/{gid}/actions")
def create_action(
    gid: str, 
    body: ActionCreate, 
    user: dict = Depends(current_user)
):
    owned_game(gid, user)

    rid = body.request_id or str(uuid.uuid4())
    existing = load_request(rid)

    if existing is not None:
        if existing["game_id"] != gid:
            raise HTTPException(
                status_code=409,
                detail="request_id already used for another game"
            )
        return existing

    request = {
        "request_id": rid,
        "game_id": gid,
        "text": body.text,
        "status": "PENDING"
    }
    save_request(rid, request)

    return request

# GET /api/v1/requests/{rid}
# Return the current state of an action request after checking game ownership.
@app.get("/api/v1/requests/{rid}")
def get_request(rid: str, user: dict = Depends(current_user)):
    request = load_request(rid)

    if request is None:
        raise HTTPException(status_code=404, detail="Request not found")

    owned_game(request["game_id"], user)

    return request

# GET /api/v1/costs
# Return all service cost records ordered by service name.


# POST /api/v1/costs
# Create and return a service cost record; reject duplicate service names.


# PUT /api/v1/costs/{i}
# Partially update an existing cost record and return the resulting record.


# DELETE /api/v1/costs/{i}
# Delete a cost record.


# POST /api/v1/costs/calculate
# Calculate per-service subtotals and the total cost for the requested duration.


# GET /api/v1/carbon
# Return all carbon profiles ordered by service name.


# POST /api/v1/carbon
# Create and return a carbon profile; reject duplicate service names.


# PUT /api/v1/carbon/{i}
# Partially update an existing carbon profile and return the resulting record.


# DELETE /api/v1/carbon/{i}
# Delete a carbon profile.


# POST /api/v1/carbon/sci
# Calculate energy, operational emissions, embodied emissions, and SCI.
