Feature: The checkout the site shows
  The site shows a git checkout of business-plan main, cloned when missing and pulled at most
  once a minute, and imports the card format from the commit it shows.

  Background:
    Given a scratch directory
    And a file "." copied from "tests/fixtures/business-plan"
    And a git repository
    And everything is committed with the message "cards"

  Scenario: A clone shows the latest commit and its cards
    Given a clone of this checkout, pulled at most once a minute
    When the clone is read
    Then the result's "commit" is "latest"
    And the result's "cards" is "["OPP-01", "OPP-02", "OPP-10"]"

  Scenario: The checkout is pulled at most once a minute
    Given a clone of this checkout, pulled at most once a minute
    And the clone was read
    And a file "opportunities/notes.md" holding "more"
    And everything is committed with the message "edit"
    When the clone is read
    Then the result's "commit" is "first"

  Scenario: Once a minute has gone, the checkout is pulled
    Given a clone of this checkout, pulled at most once a minute
    And the clone was read
    And a file "opportunities/notes.md" holding "more"
    And everything is committed with the message "edit"
    And the clone pulls on each read from now on
    When the clone is read
    Then the result's "commit" is "latest"

  Scenario: The first request clones, even soon after boot
    Given the machine booted five seconds ago
    And a clone of this checkout, pulled at most once a minute
    When the clone is read
    Then the result's "commit" is "latest"

  Scenario: A broken card is reported, not fatal
    Given a file "opportunities/OPP-98.md" holding "no front matter"
    When the checkout is read
    Then the result's "cards" is "["OPP-01", "OPP-02", "OPP-10"]"
    And the result's "problems" is "["opportunities/OPP-98.md: opportunities/OPP-98.md: no YAML front matter between --- lines"]"

  Scenario: The card format comes from the commit shown
    Given a clone of this checkout, pulled on each read
    When the clone is read
    Then the result's "NEW" is "null"

  Scenario: A new commit's card format is the one used
    Given a clone of this checkout, pulled on each read
    And the clone was read
    And the card format gains "NEW = True"
    And everything is committed with the message "the format moves"
    When the clone is read
    Then the result's "NEW" is "true"

  Scenario: A broken card format is reported, and the last one stays
    Given a clone of this checkout, pulled on each read
    And the clone was read
    And a file "bizplan/opportunities.py" holding "def broken(:"
    And everything is committed with the message "broken"
    When the clone is read
    Then the result's "cards" is "["OPP-01", "OPP-02", "OPP-10"]"
    And the result's "problems.0" is "bizplan.opportunities: SyntaxError: invalid syntax (opportunities.py, line 1)"

  Scenario: Without a card format the checkout can't be shown
    Given no card format was loaded yet
    And the file "bizplan" is removed
    And everything is committed with the message "no format"
    When the checkout is read
    Then it is refused, saying "No module named 'bizplan'"
    And the refusal's "__class__.__name__" is "ModuleNotFoundError"

  Scenario: Without a card format the site says so
    Given no card format was loaded yet
    When the card format is asked for
    Then it is refused, saying "bizplan.opportunities isn't loaded: Content.now() imports it from the checkout"
    And the refusal's "__class__.__name__" is "RuntimeError"
