# Contributing

Run the suite before opening anything:

```bash
python3 -m unittest discover -s tests -v
```

Two rules that keep this tool trustworthy:

1. A change to how a number is computed ships with a test that pins the
   number. Silent measurement drift is the one bug this repo cannot have.
2. Zero dependencies. Python 3.9+ stdlib only, single file.
