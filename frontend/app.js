import { initializeApp } from "https://www.gstatic.com/firebasejs/12.2.1/firebase-app.js";
import {
    getAuth,
    createUserWithEmailAndPassword,
    signInWithEmailAndPassword,
    signOut,
    onAuthStateChanged
} from "https://www.gstatic.com/firebasejs/12.2.1/firebase-auth.js";

import { firebaseConfig } from "./firebase-config.js";

const auth = getAuth(initializeApp(firebaseConfig));
const $ = (x) => document.getElementById(x);

let gid = localStorage.gid || "";

async function H() {
    return {
        "Content-Type": "application/json",
        "Authorization": "Bearer " + await auth.currentUser.getIdToken()
    };
}

async function newGame() {
    let d = await (
        await fetch("/api/v1/games", {
            method: "POST",
            headers: await H()
        })
    ).json();

    gid = d.game_id;
    localStorage.gid = gid;

    $("history").innerHTML = "";

    render(d);
    add("System", "A new expedition begins.");
}

async function load() {
    let r = await fetch("/api/v1/games/" + gid, {
        headers: await H()
    });

    if (!r.ok) {
        return newGame();
    }

    render(await r.json());
}

function render(d) {
    $("status").textContent = d.status;
    $("turn").textContent = "Turn " + d.turn;
    $("room").textContent = d.room.name;
    $("description").textContent = d.room.description;

    $("exits").innerHTML = d.room.exits
        .map((x) => "<span>" + x + "</span>")
        .join("");

    $("inventory").innerHTML = d.inventory.length
        ? d.inventory
              .map((x) => "<span>" + x.replaceAll("_", " ") + "</span>")
              .join("")
        : "Nothing collected";

    $("progress").style.width =
        Math.min(
            100,
            (d.inventory.filter((x) => x.startsWith("fragment_")).length / 3) * 100
        ) + "%";
}

function add(w, t) {
    let d = document.createElement("div");
    d.className = "entry";

    let b = document.createElement("b");
    b.textContent = w;

    d.append(
        b,
        document.createElement("br"),
        document.createTextNode(t)
    );

    $("history").append(d);
}

async function send(t) {
    if (!t.trim()) {
        return;
    }

    add("You", t);
    $("pipeline").className = "busy";

    let q = await (
        await fetch("/api/v1/games/" + gid + "/actions", {
            method: "POST",
            headers: await H(),
            body: JSON.stringify({
                text: t
            })
        })
    ).json();

    for (let i = 0; i < 60; i++) {
        await new Promise((r) => setTimeout(r, 500));

        let d = await (
            await fetch("/api/v1/requests/" + q.request_id, {
                headers: await H()
            })
        ).json();

        if (d.status === "COMPLETED") {
            add("Game", d.game_result.message);
            $("narrative").textContent = d.ai_response.message;
            render(d.game_state);
            $("pipeline").className = "";
            return;
        }
    }

    $("pipeline").className = "";
    add("System", "Pipeline timeout");
}

$("register").onclick = () =>
    createUserWithEmailAndPassword(
        auth,
        $("email").value,
        $("password").value
    ).catch((e) => {
        $("error").textContent = e.message;
    });

$("login").onclick = () =>
    signInWithEmailAndPassword(
        auth,
        $("email").value,
        $("password").value
    ).catch((e) => {
        $("error").textContent = e.message;
    });

$("logout").onclick = () => signOut(auth);
$("newGame").onclick = newGame;

$("form").onsubmit = (e) => {
    e.preventDefault();

    let t = $("command").value;
    $("command").value = "";

    send(t);
};

document
    .querySelectorAll("[data-cmd]")
    .forEach((b) => (b.onclick = () => send(b.dataset.cmd)));

fetch("/health").then(
    (r) =>
        ($("health").textContent = r.ok
            ? "● services online"
            : "● unavailable")
);

onAuthStateChanged(auth, (u) => {
    $("auth").hidden = !!u;
    $("game").hidden = !u;

    if (u) {
        gid ? load() : newGame();
    } else {
        gid = "";
        localStorage.removeItem("gid");
    }
});
