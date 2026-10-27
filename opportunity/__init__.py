"""The opportunity site: the team reads, comments on, reviews and proposes
changes to the opportunity cards (opportunities/OPP-nn.md) and the research
reports under them (opportunities/research/).

The cards stay in git: the site reads a checkout of business-plan main and
turns edits into pull requests. Comments and reviews are its own, in
PostgreSQL, each tied to the commit it was made on.
"""
