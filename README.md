# SafePlate

An allergen checker for a dining hall. It reads the messy labels the kitchen
actually writes, and tells a diner whether they can eat something. When it is not
sure, it says so instead of guessing.

## Running it

```bash
pip install streamlit pydantic requests pytest

streamlit run app.py             # the app. runs offline, from cache.json
pytest -q                        # 18 tests
```

**You do not need an API key to run any of that.** The menu has already been read and
the readings are committed in `cache.json`, so the app and the tests both work with no
network at all. That is not a shortcut, it is the design: once a label has been read,
nothing needs to read it again.

You only need a key if you want to re-read the menu yourself, or press the "re-read
this label" button in the app:

```bash
cp .env.example .env             # then paste your key into .env
python extract.py                # reads the menu, fills cache.json
```

A free Groq key takes a minute and needs no card: https://console.groq.com. The key is
read from `.env`, which is gitignored. A real `GROQ_API_KEY` environment variable
overrides the file, so a deployed host or a CI runner needs no `.env` at all.

## The idea, in one paragraph

The obvious way to build this is to ask a language model "here is a label, is it
safe for a peanut allergy". That is the one thing I did not do. A model is a fluent
guesser, it will answer confidently about a label it did not really understand, and
the label itself is untrusted text that can talk it into things. So the job is split
in two. The model reads, and it only reads: it turns a label into a list of
allergens with a quote from the label for each one. Then a short Python function
decides. The model is never asked whether food is safe, and it never answers that
question.

The payoff is that the decision is auditable. You can read `engine.py` end to end,
and afterwards you will be able to say exactly why any item is red, amber or green.
You cannot do that with "the model thought it looked fine".

## Where to look, and in what order

If you are marking this and want the shortest path through it:

| File | What it is |
|---|---|
| `engine.py` | **Start here.** Every safety decision in the project. No model, no network, no files. |
| `models.py` | The shapes both sides speak. Two of the three rules below are enforced here, as validators. |
| `extract.py` | The only file that touches a model or the network. Reads a label, then checks the reading. |
| `app.py` | The screen. It does no thinking, it just draws what the engine returns. |
| `test_engine.py` | The traps. Each test is a way somebody could get hurt. |
| `menu.json` | The kitchen's labels, kept exactly as written, mess and all. |

The comments are deliberately generous, because the aim is something a non-programmer
could read aloud, and because most of what I got wrong on this project was hiding in
the gap between what a comment claimed and what the code actually did.

## How it fits together

```
menu.json        the labels, kept verbatim, including "peanuts??" and "null"
    |
extract.py       the model reads the label into findings, then a second call
    |            checks that reading. both answers are cached against a hash
    |            of the label text, so the app needs no network afterwards.
    v
models.py        the schema. rejects an allergen it does not recognise, and
    |            rejects any finding that cannot quote the label.
    v
engine.py        decide(your allergens, the reading, did it verify) -> a colour
    |            plain Python. this is the only place safety is decided.
    v
app.py           one row per dish, with a panel showing the working
```

## The three rules

1. **The model never decides whether food is safe.** It reads labels and it checks
   its own reading. `engine.py` decides. Nothing else does.
2. **Every finding has to quote the label.** No quote, no finding. This one is
   enforced by a validator in `models.py`, not by asking the model politely.
3. **Green has to be earned, and it is never the default.** A missing label is
   amber. A vague label is amber. An item nobody has read is amber. An item the two
   models disagreed about is amber. And an allergen match is red even when the label
   was only hedging.

## Green has to get past five checks

`decide()` runs these in order, and an item only comes out green if it survives all
five:

1. the two readings of the label agreed with each other
2. the label was actually readable, not "see chef" and not empty
3. none of the diner's allergens were found in it
4. **and the label text itself agrees with that.** Plain Python scans the raw label
   for words belonging to the diner's allergens. If the label says "butter" and the
   reading somehow reported no milk, the item cannot go green.
5. only then, green

Check 4 is the one I added last, and it is the one that closes the obvious hole.
Without it the engine is deterministic but its input is entirely under the model's
control, so a model that says "clean, nothing found" produces a green every time, and
the model ends up deciding after all. Check 4 is ordinary string matching against the
raw text, with no model involved in it.

## What it deliberately does not do

It reads labels. That is all it can honestly claim to do.

It knows nothing about cross-contamination or what actually happens in the kitchen,
because a label cannot tell you that. This is exactly why an unclear label goes
amber and says "ask the counter", rather than trying to be clever.

It does not store the diner's allergies. They sit in memory for the session and are
never written down. Allergies count as health data under UK GDPR, and there is no
good reason for a menu board to be keeping any, so it keeps none. There are no
accounts and no database. The only thing written to disk is the cache of label
readings, which contains no personal data at all. Streamlit's usage tracking is
switched off in `.streamlit/config.toml`.

## The other files

- **`BUILD_LOG.md`** is what broke while I was building this, what I changed, and what
  happened. It covers the two silent routes to a false green that I only found by
  going looking for them after every test was already passing, and the prompt
  injection that did compromise one of the two models and still changed nothing.
- **`cache.json`** is committed on purpose. It holds the model's readings of the menu
  and the second model's checks on them, which is what lets this run with no key. It
  contains menu labels and nothing else.
