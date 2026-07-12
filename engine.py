"""The safety engine. This is the file to read if you only read one.

Every decision about whether to warn a diner is made here, in plain Python. There
is no network call, no file access and no language model in this file. That is
deliberate. A model can be confidently wrong, and you cannot audit "the model
thought it looked fine", but you can audit an if-statement.

The model's job, over in extract.py, is only to turn a messy label into a list of
findings. This file decides what those findings mean for a particular diner.
"""
import re
from dataclasses import dataclass

from models import Extraction

# If several of the diner's allergens turn up, they all make the item red anyway.
# This ranking only picks which one we quote in the message, so we lead with the
# finding that has the strongest evidence behind it.
STATUS_SEVERITY = {"present": 3, "may_contain": 2, "uncertain": 1}

# Words we look for in the raw label ourselves, without asking the model.
# Gate 4 in decide() uses this. Singular forms only: the match below also allows a
# trailing "s". Whole words only, so "nut" does not match inside "peanuts", which
# matters because peanuts and tree nuts are separate categories in the FSA list and
# a peanut label must not raise a tree nut warning.
KEYWORDS = {
    "celery": ["celery", "celeriac"],
    "cereals containing gluten": ["gluten", "wheat", "flour", "bread", "oat",
                                  "panko", "barley", "rye", "pasta", "semolina"],
    "crustaceans": ["prawn", "shrimp", "crab", "lobster"],
    "eggs": ["egg", "mayo", "mayonnaise"],
    "fish": ["fish", "tuna", "salmon", "anchovy", "cod"],
    "lupin": ["lupin"],
    "milk": ["milk", "butter", "cheese", "cheddar", "mozzarella", "halloumi",
             "cream", "yoghurt", "yogurt"],
    "molluscs": ["mussel", "oyster", "squid", "clam", "scallop"],
    "mustard": ["mustard"],
    "peanuts": ["peanut", "nut"],
    "sesame": ["sesame", "tahini"],
    "soybeans": ["soy", "soya", "soybean", "tofu", "edamame"],
    "sulphites": ["sulphite", "sulfite"],
    "tree nuts": ["nut", "almond", "cashew", "walnut", "hazelnut", "pecan",
                  "pistachio"],
}


@dataclass
class Verdict:
    colour: str      # "RED", "AMBER" or "GREEN"
    reason: str      # the one line the diner reads


def missed_by_the_parse(user_allergens: set[str], ex: Extraction) -> set[str]:
    """Allergens whose words appear in the label but which the model never reported.

    This is the one place we refuse to take the model's word for anything. We read
    the raw label ourselves with ordinary string matching. If the label says
    "butter" and the model somehow reported no milk, that is a miss, and a miss
    means we will not show green.
    """
    reported = {f.allergen for f in ex.findings}
    label = ex.raw_label.lower()
    return {a for a in user_allergens - reported
            if any(re.search(rf"\b{re.escape(w)}s?\b", label)
                   for w in KEYWORDS.get(a, []))}


def decide(user_allergens: set[str], ex: Extraction, verified: bool) -> Verdict:
    """Turn one reading of one label into one colour, for one diner.

    Five checks, in this order. An item only comes out green if it survives all of
    them. Anything we are unsure about comes out amber, which means "go and ask a
    human", and never green.
    """
    # 1. Two models read the same label and disagreed about it. We do not know
    #    which one is right, so we do not pretend to.
    if not verified:
        return Verdict("AMBER", "the two readings disagree, ask the counter")

    # 2. The label itself was vague ("see chef") or simply absent ("null"). An
    #    absent label tells us nothing, and nothing is not the same as no allergens.
    if ex.data_quality != "clean":
        return Verdict("AMBER", ex.quality_reason + ", ask the counter")

    # 3. Something the diner avoids is in the label. Red, even if the label was only
    #    hedging ("peanuts??"), because a maybe on your allergen is still a no.
    hits = [f for f in ex.findings if f.allergen in user_allergens]
    if hits:
        worst = max(hits, key=lambda f: STATUS_SEVERITY[f.status])
        return Verdict("RED", f"{worst.allergen}: the label says "
                              f"'{worst.evidence}'")

    # 4. The model says the diner is fine, but the label text says otherwise. We
    #    believe the label. This is what stops a bad or manipulated reading from
    #    turning into a green, and it is plain string matching, so there is no
    #    prompt here for anyone to interfere with.
    missed = missed_by_the_parse(user_allergens, ex)
    if missed:
        return Verdict("AMBER", f"the label mentions {', '.join(sorted(missed))} "
                                "but the reading did not pick it up, "
                                "ask the counter")

    # 5. Clean label, both readings agree, nothing the diner avoids, and the raw
    #    text backs that up. Note the wording. It is about this diner's allergens,
    #    and it never claims the food is safe, because a label cannot tell us that.
    return Verdict("GREEN", "none of the allergens you picked are declared on "
                            f"this label: '{ex.raw_label}'")


def verdict_for(user_allergens: set[str], ex, verified: bool) -> Verdict:
    """Same as decide(), but for an item we have not read yet.

    The app calls this one. An item with no cached reading is amber. We do not have
    an opinion on food nobody has looked at.
    """
    if ex is None:
        return Verdict("AMBER", "this label has not been read yet, ask the counter")
    return decide(user_allergens, ex, verified)
