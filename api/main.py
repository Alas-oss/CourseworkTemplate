import sqlite3
import threading
import uuid

from fastapi import Depends, FastAPI, HTTPException

import messaging
from database import (
    connection,
    initialise_database,
    list_rows,
    insert_row,
    update_row,
    delete_row
)
from firebase_authentication import get_current_user
from game import fresh, present
from models import *
from pipeline import (
    expire_if_stuck,
    handle_llm_result,
    handle_semantic_result,
    public_request
)
from state import (
    delete_request,
    load_game,
    load_request,
    ping,
    save_game,
    save_request
)
from sci import calculate_sci

# Create the AI Archive API.
app = FastAPI(title="The AI Archive API")

def owned_game(gid, user):
    state = load_game(gid)

    if state is None or state["owner"] != user["uid"]:
        raise HTTPException(status_code=404, detail="Game not found")

    return state

# Initialise persistent data and start background result processing.
@app.on_event("startup")
def startup():
    initialise_database()

    if messaging.ENABLED:
        for queue, handler in (
            ("semantic.results", handle_semantic_result),
            ("llm.results", handle_llm_result),
        ):
            threading.Thread(
                target=messaging.consume,
                args=(queue, handler),
                daemon=True
            ).start()

# GET /health
# Confirm that the API and its required state service are available.
@app.get("/health")
def health():
    try:
        with connection() as c:
            c.execute("SELECT 1")
    except Exception:
        raise HTTPException(status_code=503, detail="Database unavailable")

    try:
        ping()
    except Exception:
        raise HTTPException(
            status_code=503,
            detail="State service unavailable"
        )

    return {
        "status": "healthy",
        "database": "sqlite",
        "authentication": "firebase"
    }
# GET /api/v1/authentication/me
# Return the identity of the authenticated user.
@app.get("/api/v1/authentication/me")
def me(user: dict = Depends(get_current_user)):
    return user


# POST /api/v1/games
# Create a new game owned by the authenticated user and return its initial state.
@app.post("/api/v1/games")
def create_game(user: dict = Depends(get_current_user)):
    gid = str(uuid.uuid4())
    state = fresh(user["uid"])
    save_game(gid, state)

    return {"game_id": gid, **present(state)}

# GET /api/v1/games/{gid}
# Return a game only when it exists and belongs to the authenticated user.
@app.get("/api/v1/games/{gid}")
def get_game(gid: str, user:dict = Depends(get_current_user)):
    state = owned_game(gid, user)

    return {"game_id": gid, **present(state)}

# POST /api/v1/games/{gid}/actions
# Accept a player command and create an asynchronous request.
# Return the existing request when the same request_id is submitted again.
@app.post("/api/v1/games/{gid}/actions")
def create_action(
    gid: str,
    body: ActionCreate,
    user: dict = Depends(get_current_user)
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

        return public_request(existing)

    request = {
        "request_id": rid,
        "game_id": gid,
        "text": body.text,
        "status": "PENDING"
    }
    save_request(rid, request)

    try:
        messaging.publish(
            "semantic.requests",
            messaging.envelope(
                "semantic.requested", rid, {"text": body.text}
            )
        )
    except Exception:
        delete_request(rid)
        raise HTTPException(
            status_code=503,
            detail="Message broker unavailable"
        )

    return request

# GET /api/v1/requests/{rid}
# Return the current state of an action request after checking game ownership.
@app.get("/api/v1/requests/{rid}")
def get_request(rid: str, user: dict = Depends(get_current_user)):
    request = load_request(rid)

    if request is None:
        raise HTTPException(status_code=404, detail="Request not found")

    owned_game(request["game_id"], user)

    request = expire_if_stuck(request)

    return public_request(request)

# GET /api/v1/costs
# Return all service cost records ordered by service name.
def cost_out(row):
    row["enabled_by_default"] = bool(row["enabled_by_default"])
    return row

def create_record(table, data):
    try:
        return insert_row(table, data)
    except sqlite3.IntegrityError:
        raise HTTPException(
            status_code=409,
            detail="Duplicate service_name or invalid values"
        )

def update_record(table, i, body):
    data = body.model_dump(exclude_none=True)

    if not data:
        raise HTTPException(
            status_code=400,
            detail="No fields to update"
        )

    row = update_row(table, i, data)
    if row is None:
        raise HTTPException(status_code=404, detail="Record not found")


    return row


def delete_record(table, i):
    if not delete_row(table, i):
        raise HTTPException(status_code=404, detail="Record not found")


    return {"deleted": i}

@app.get("/api/v1/costs")
def list_costs():
    return [cost_out(r) for r in list_rows("microservice_costs")]
# POST /api/v1/costs
# Create and return a service cost record; reject duplicate service names.
@app.post("/api/v1/costs", status_code=201)
def create_cost(body: CostCreate):
    return cost_out(
        create_record("microservice_costs", body.model_dump())
    )

# PUT /api/v1/costs/{i}
# Partially update an existing cost record and return the resulting record.
@app.put("/api/v1/costs/{i}")
def update_cost(i: int, body: CostUpdate):
    return cost_out(update_record("microservice_costs", i, body))


# DELETE /api/v1/costs/{i}
# Delete a cost record.
@app.delete("/api/v1/costs/{i}")
def delete_cost(i: int):
    return delete_record("microservice_costs", i)


# POST /api/v1/costs/calculate
# Calculate per-service subtotals and the total cost for the requested duration.
@app.post("/api/v1/costs/calcualte")
def calculate_costs(body: CostCalculation):
    rows = [cost_out(r) for r in list_rows("microservice_costs")]

    if body.services is None:
        chosen = [r for r in rows if r["enabled_by_default"]]
    else:
        by_name = {r["service_name"]: r for r in rows}
        missing = [s for s in body.services if s not in by_name]

        if missing:
            raise HTTPException( status_code=404,
                detail="Unknown services: " + ", ".join(missing)
            )

        chosen = [by_name[s] for s in dict.fromkeys(body.services)]

    if any(n < 0 for n in body.instances.values()):
        raise HTTPException(
            status_code=422,
            detail="Instance counts cannot be negative"
        )

    currencies = {r["currency"] for r in chosen}

    if len(currencies) > 1:
        raise HTTPException(
            status_code=422,
            detail="Selected services use different currencies"
        )

    lines = []
    total = 0.0

    for r in chosen:
        count = body.instances.get(r["service_name"], 1)
        subtotal = r["cost_per_hour"] * count * body.hours
        total += subtotal

        lines.append({
            "service_name": r["service_name"],
            "cost_per_hour": r["cost_per_hour"],
            "instances": count, 
            "hours": body.hours,
            "subtotal": rounds(subtotal, 6)
        })

    return {
        "hours": body.hours,
        "currency": currencies.pop() if currencies else "GBP",
        "services": lines,
        "total": round(total, 6)
    }

# GET /api/v1/carbon
# Return all carbon profiles ordered by service name.
@app.get("/api/v1/carbon")
def list_carbon():
    return list_rows("carbon_profiles")

# POST /api/v1/carbon
# Create and return a carbon profile; reject duplicate service names.
@app.post("/api/v1/carbon", status_code=201)
def create_carbon(body: CarbonCreate):
    return create_record("carbon_profiles", body.model_dump())

# PUT /api/v1/carbon/{i}
# Partially update an existing carbon profile and return the resulting record.
@app.put("/api/v1/carbon/{i}")
def update_carbon(i: int, body: CarbonUpdate):
    return update_record("carbon_profiles", i, body)

# DELETE /api/v1/carbon/{i}
# Delete a carbon profile.
@app.delete("/api/v1/carbon/{i}")
def delete_carbon(i: int):
    return delete_record("carbon_profiles", i)

# POST /api/v1/carbon/sci
# Calculate energy, operational emissions, embodied emissions, and SCI.
@app.post("/api/v1/carbon/sci")
def carbon_sci(body: SCICalculation):
    profiles = list_rows("carbon_profiles")

    if body.services is not None:
        if not body.services:
            raise HTTPException(
                status_code=422,
                detail="services cannot be an empty list"
            )

        by_name = {p["service_name"]: p for p in profiles}
        missing = [s for s in body.services if s not in by_name]

        if missing:
            raise HTTPException(
                status_code=404,
                detail="Unknown services: " + ", ".join(missing)
            )

        profiles = [by_name[s] for s in dict.fromkeys(body.services)]

    try:
        return calculate_sci(profiles, body.functional_units)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error))
    

@app.post("/api/v1/costs/calculate")
def calculate_costs(body: CostCalculation):
    rows = [cost_out(r) for r in list_rows("microservice_costs")]

    if body.services is None:
        chosen = [r for r in rows if r["enabled_by_default"]]
    else:
        by_name = {r["service_name"]: r for r in rows}
        missing = [s for s in body.services if s not in by_name]

        if missing:
            raise HTTPException(
                status_code=404,
                detail="Unknown services: " + ", ".join(missing)
            )

        chosen = [by_name[s] for s in dict.fromkeys(body.services)]

    if any(n < 0 for n in body.instances.values()):
        raise HTTPException(
            status_code=422,
            detail="Instance counts cannot be negative"
        )

    currencies = {r["currency"] for r in chosen}

    if len(currencies) > 1:
        raise HTTPException(
            status_code=422,
            detail="Selected services use different currencies"
        )

    lines = []
    total = 0.0

    for r in chosen:
        count = body.instances.get(r["service_name"], 1)
        subtotal = r["cost_per_hour"] * count * body.hours
        total += subtotal

        lines.append({
            "service_name": r["service_name"],
            "cost_per_hour": r["cost_per_hour"],
            "instances": count,
            "hours": body.hours,
            "subtotal": round(subtotal, 6)
        })

    return {
        "hours": body.hours,
        "currency": currencies.pop() if currencies else "GBP",
        "services": lines,
        "total": round(total, 6)
    }
