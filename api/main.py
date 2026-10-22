from database import connection, initialise_database
from game import fresh, present, apply
from models import *


# Create the AI Archive API.
# app = 




# Initialise persistent data and start background result processing.
@app.on_event("startup")
def startup():
    initialise_database()

    threading.Thread(
        target=consume,
        daemon=True
    ).start()


# GET /health
# Confirm that the API and its required state service are available.


# GET /api/v1/authentication/me
# Return the identity of the authenticated user.


# POST /api/v1/games
# Create a new game owned by the authenticated user and return its initial state.


# GET /api/v1/games/{gid}
# Return a game only when it exists and belongs to the authenticated user.


# POST /api/v1/games/{gid}/actions
# Accept a player command and create an asynchronous request.
# Return the existing request when the same request_id is submitted again.


# GET /api/v1/requests/{rid}
# Return the current state of an action request after checking game ownership.


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
