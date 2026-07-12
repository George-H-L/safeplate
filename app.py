"""The screen a diner actually sees.

This file does no thinking. It reads the cached extractions off disk, asks the
engine for a colour, and draws the result. If you are reading this to work out how
the app decides anything, you are in the wrong file: that all happens in engine.py.

The allergen selection lives in Streamlit's session state and is never written
anywhere. Allergies are health data, and the safest place to keep health data is
nowhere.
"""
import hashlib
import json
from pathlib import Path

import streamlit as st

import extract
from engine import verdict_for
from models import FSA_14, Extraction, Verification

HERE = Path(__file__).parent

# Green first, because the useful question is "what can I eat", not "what can't I".
ORDER = {"GREEN": 0, "AMBER": 1, "RED": 2}

# The word next to the colour. A safety signal should never rely on colour alone:
# roughly one man in twelve cannot reliably separate red from green.
STATUS = {"GREEN": "no match", "AMBER": "check", "RED": "avoid"}


def cached(label):
    """Look this label up in cache.json. No network call, ever."""
    path = HERE / "cache.json"
    cache = json.loads(path.read_text()) if path.exists() else {}
    sha = hashlib.sha256(label.encode()).hexdigest()
    ex = Extraction(**cache[f"extract:{sha}"]) if f"extract:{sha}" in cache else None
    v = cache.get(f"verify:{sha}")
    # No verification on file means this was never verified, which is not the same
    # as verified and fine. Green has to be earned, so this defaults to False.
    verified = Verification(**v).verdict == "agree" if v else False
    return ex, verified


st.set_page_config(page_title="SafePlate", layout="centered")
st.markdown(f"<style>{(HERE / 'style.css').read_text()}</style>",
            unsafe_allow_html=True)

st.title("SafePlate")
st.caption("Today's menu, read against the allergens you need to avoid. "
           "Every colour on this page is decided by a plain Python function, "
           "not by the language model that read the labels.")

avoid = set(st.sidebar.multiselect("I need to avoid", FSA_14))
st.sidebar.caption("Kept in memory for this session only. Never saved to disk.")

if not avoid:
    st.info("Pick your allergens in the sidebar. Until you do, nothing can be "
            "matched against them, so every readable label shows as no match.")

menu = json.loads((HERE / "menu.json").read_text())

rows = []
for m in menu:
    ex, verified = cached(m["raw_label"])
    rows.append((verdict_for(avoid, ex, verified), m, ex, verified))
rows.sort(key=lambda r: ORDER[r[0].colour])

for v, m, ex, verified in rows:
    tone = v.colour.lower()
    st.markdown(
        f"<div class='row row-{tone}'>"
        f"<span class='status status-{tone}'>{STATUS[v.colour]}</span><br>"
        f"<span class='item'>{m['item_name']}</span><br>"
        f"<span class='reason'>{v.reason}</span></div>",
        unsafe_allow_html=True)

    with st.expander("Show the working"):
        st.markdown("**What the kitchen wrote**")
        st.markdown(f"<span class='label'>{m['raw_label']}</span>",
                    unsafe_allow_html=True)
        st.markdown(f"**What the rule said**  \n`{v.colour}` {v.reason}")
        st.markdown(f"**Did the second model agree with the reading?**  \n"
                    f"{'Yes' if verified else 'No, so this cannot go green'}")
        st.markdown("**What the model pulled out of the label**")
        st.json(ex.model_dump() if ex else {"note": "not parsed yet, so amber"})

        if st.button("Re-read this label now", key=m["item_name"]):
            # extract() never raises. It catches API errors itself and hands back a
            # "missing" reading, so we check what came back rather than waiting for
            # an exception that will not arrive. Otherwise this button would happily
            # report success on a call that never happened.
            fresh = extract.extract(m)
            if fresh.quality_reason == "live call unavailable":
                st.warning("Could not reach the model. Still showing the cached "
                           "reading, which is why the app keeps working offline.")
            else:
                extract.verify(m["raw_label"], fresh)
                st.success("Re-read. Refresh the page to see the updated verdict.")

st.divider()
st.caption("Green means none of the allergens you picked are declared on the "
           "label. It does not mean the food is safe. This app reads labels. It "
           "knows nothing about what happens in the kitchen, so it cannot see "
           "cross-contamination.")
