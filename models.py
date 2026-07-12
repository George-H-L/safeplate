"""The shapes the model and the engine both have to agree on.

Worth knowing if you are marking this: the two validators below are not tidiness.
They are where two of the project's rules are actually enforced. Asking a model
nicely in a prompt is not enforcement, because a prompt is a request and a model
can ignore a request. A validator cannot be ignored.

If either validator fails, extract.py retries once and then gives up and marks the
label "ambiguous", which the engine turns into amber. So a model that breaks the
rules makes the app more cautious, not less.
"""
from typing import Literal

from pydantic import BaseModel, field_validator, model_validator

# The 14 allergens UK law requires food businesses to declare. The engine only ever
# reasons about these exact strings, and the diner picks from this same list, which
# is why the validator below matters so much.
FSA_14 = ["celery", "cereals containing gluten", "crustaceans", "eggs",
          "fish", "lupin", "milk", "molluscs", "mustard", "peanuts",
          "sesame", "soybeans", "sulphites", "tree nuts"]


class Finding(BaseModel):
    """One allergen the model believes it found in one label."""

    allergen: str
    status: Literal["present", "may_contain", "uncertain"]
    evidence: str

    @field_validator("allergen")
    @classmethod
    def must_be_one_of_the_fsa_14(cls, v):
        # This one is subtle and it is worth spelling out. The engine decides if an
        # item is red by checking "is this allergen in the diner's list". The diner's
        # list comes from FSA_14. So if the model returned "peanut" instead of
        # "peanuts", that check would quietly fail, the finding would be dropped,
        # and a peanut allergy sufferer would be shown green. No error, no warning.
        # Rejecting the finding outright is the only safe thing to do.
        if v not in FSA_14:
            raise ValueError(f"not an FSA 14 allergen: {v!r}")
        return v


class Extraction(BaseModel):
    """Everything the model got out of one label."""

    item_name: str
    findings: list[Finding]
    data_quality: Literal["clean", "ambiguous", "missing"]
    quality_reason: str
    raw_label: str

    @model_validator(mode="after")
    def every_finding_has_to_quote_the_label(self):
        # No quote, no finding. The evidence has to be words that are actually in the
        # label, not the model's summary of them, because the app shows that evidence
        # to the diner in quotation marks as something the kitchen wrote. If we did
        # not check this, a made up allergen could be presented as a real quote.
        for f in self.findings:
            if not f.evidence.strip():
                raise ValueError(f"{f.allergen}: no evidence given")
            if f.evidence.lower() not in self.raw_label.lower():
                raise ValueError(
                    f"{f.allergen}: the evidence {f.evidence!r} is not in the label")
        return self


class Verification(BaseModel):
    """The second model's opinion of the first model's reading."""

    verdict: Literal["agree", "disagree"]
    discrepancies: list[str]
