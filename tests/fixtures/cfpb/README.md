# CFPB Test Fixtures

Files in this directory are hand-authored synthetic contract fixtures. They are
not extracts, redactions, or paraphrases of real Consumer Complaint Database
records.

Fixture rules:

- narratives must begin with `SYNTHETIC TEST RECORD`;
- companies and identifiers must be visibly synthetic;
- do not include names, addresses, account numbers, email addresses, phone
  numbers, or other personal data;
- keep fixtures to five hits or fewer;
- use taxonomy placeholders until the target taxonomy is approved; and
- never replace a synthetic record by copying a live API response.

The response fixture exists to test parsing and schema safeguards without making
network calls or committing raw CFPB narratives.
