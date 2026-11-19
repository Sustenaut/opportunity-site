Feature: Proposing changes by pull request
  An edit to a card or a new research report becomes a pull request in business-plan, opened
  by the site's GitHub App; the site never writes to main.

  Background:
    Given a scratch directory
    And a file "." copied from "tests/fixtures/business-plan"
    And a git repository
    And everything is committed with the message "cards"
    And the site shows this checkout, on a laptop
    And the environment sets "OPPORTUNITY_DEV_USER" to "reviewer@example.org"
    And requests come from "http://testserver"

  Scenario: Front matter round trips for every card
    When every card's front matter is split and joined again
    Then the result is:
      """
      {"OPP-01": {"joined": true, "edited": true}, "OPP-02": {"joined": true, "edited": true}, "OPP-10": {"joined": true, "edited": true}}
      """

  Scenario: An edit opens a pull request naming the editor
    When I propose an edit to "OPP-10" with every field, changing:
      | field        | value                |
      | f:confidence | high (0.85)          |
      | note         | The sandbox replied. |
    And the pull requests proposed are read
    Then the answer is 200
    And the answer includes "pull/101"
    And the result has 1 pull request
    And the result's "0.slug" is "OPP-10"
    And the result's "0.user" is "reviewer"
    And the result's "0.title" is "OPP-10: edit from the opportunity site"
    And the result's "0.changes.0.path" is "opportunities/OPP-10.md"

  Scenario: The edit changes the confidence alone, keeping the other fields' comments
    When I propose an edit to "OPP-10" with every field, changing:
      | field        | value                |
      | f:confidence | high (0.85)          |
      | note         | The sandbox replied. |
    And the card the pull request proposes is read
    Then the result is:
      """
      ---
      id: OPP-10
      name: Example sign-in work
      kind: platform
      confidence: high (0.85)
      kill_point: stop if the test fails # runs on the shared Hetzner server
      levels: 2
      hours: 40
      ---
      # Example sign-in work

      ## Why

      Made up for the tests.

      """

  Scenario: The edit starts from the card as the checkout has it
    When I propose an edit to "OPP-10" with every field, changing:
      | field        | value       |
      | f:confidence | high (0.85) |
    And the card the pull request started from is read
    Then the result is:
      """
      ---
      id: OPP-10
      name: Example sign-in work
      kind: platform
      confidence: medium
      kill_point: stop if the test fails # runs on the shared Hetzner server
      levels: 2
      hours: 40
      ---
      # Example sign-in work

      ## Why

      Made up for the tests.

      """

  Scenario: The pull request says who proposed the edit, and why
    When I propose an edit to "OPP-10" with every field, changing:
      | field        | value                |
      | f:confidence | high (0.85)          |
      | note         | The sandbox replied. |
    And the body of the pull request proposed is read
    Then the result matches "An edit to OPP-10 Example sign-in work, proposed by **reviewer@example.org** on the opportunity site (https://opportunity.sustenaut.eu), starting from *.*The sandbox replied.*Merging this changes the card for everyone; until then the site shows main as it is."

  Scenario Outline: An edit that doesn't read cleanly opens nothing
    When I propose an edit to "OPP-10" with only:
      | field   | value   |
      | <field> | <value> |
    And the pull requests proposed are read
    Then the answer is 422
    And the answer includes "<message>"
    And the result is empty

    Examples:
      | field        | value           | message                                                   |
      | f:kill_point | Stop: no buyers | front matter is not valid YAML: quote values that contain |
      | f:name       |                 | A card needs a name                                       |
      | note         | nothing else    | Nothing changed                                           |

  Scenario: An edit made on a card changed on main since opens nothing
    Given someone has changed the card on main since
    When I propose an edit to "OPP-10" with only:
      | field        | value |
      | f:confidence | low   |
    And the pull requests proposed are read
    Then the answer is 422
    And the answer includes "changed on main"
    And the result is empty

  Scenario: The edit form says what a card holds
    When I GET "/c/OPP-10/edit"
    Then the answer is 200
    And the answer includes "No dates or build details in opportunity cards: a card says what is true when it is done"

  Scenario Outline: A research report that can't be added says why
    When I propose the research report:
      | field   | value                                       |
      | slug    | <slug>                                      |
      | title   | Who pays for wallet sign-in?                |
      | cards   | <cards>                                     |
      | summary | Buyers of relying-party integration.        |
      | sources | <sources>                                   |
      | body    | ## Verdict\n\nSome do.                      |
    And the pull requests proposed are read
    Then the answer is 422
    And the answer includes "<message>"
    And the result is empty

    Examples:
      | slug                   | cards  | sources                                    | message                                         |
      | wallet-relying-parties | OPP-99 | https://example.org/a                      | No such cards: OPP-99                           |
      | example-market         | OPP-10 | https://example.org/a                      | There is already a report called example-market |
      | wallet-relying-parties | OPP-10 | not a url                                  | List the sources, one web address per line      |

  Scenario: A research report is added by pull request
    When I propose the research report:
      | field   | value                                       |
      | slug    | wallet-relying-parties                      |
      | title   | Who pays for wallet sign-in?                |
      | cards   | opp-10, OPP-01                              |
      | summary | Buyers of relying-party integration.        |
      | sources | https://example.org/a\nhttps://example.org/b |
      | body    | ## Verdict\n\nSome do.                      |
    And the pull requests proposed are read
    Then the answer is 200
    And the result's "0.changes.0.path" is "opportunities/research/wallet-relying-parties.md"
    And the result's "0.changes.0.old" is "null"
    And the result's "0.title" is "Research report: Who pays for wallet sign-in?"

  Scenario: A research report proposed reads back through the card format
    When I propose the research report:
      | field   | value                                       |
      | slug    | wallet-relying-parties                      |
      | title   | Who pays for wallet sign-in?                |
      | cards   | opp-10, OPP-01                              |
      | summary | Buyers of relying-party integration.        |
      | sources | https://example.org/a\nhttps://example.org/b |
      | body    | ## Verdict\n\nSome do.                      |
    And the report proposed is read through the card format
    Then the result's "cards" is "["OPP-10", "OPP-01"]"
    And the result's "sources" is "["https://example.org/a", "https://example.org/b"]"
    And the result's "warning" is "null"
    And the result's "first line" is "# Who pays for wallet sign-in?"

  Scenario Outline: Branch names count up past the highest taken
    When a branch name is made for "OPP-10" by "david", with the branches "<taken>"
    Then the result is "<branch>"

    Examples:
      | taken                                                                                         | branch                     |
      | []                                                                                            | opportunity/OPP-10-david-1 |
      | ["opportunity/OPP-10-david-1", "opportunity/OPP-10-david-7", "opportunity/OPP-10-david-x"] | opportunity/OPP-10-david-8 |

  Scenario: The GitHub App refuses an edit made on content since changed
    Given the GitHub App on recorded answers, with OPP-10 holding "old" on main
    When the app proposes OPP-10 by "david", from "older" to "new"
    Then it is refused, saying "opportunities/OPP-10.md has changed on main since this edit began"
    And the refusal's "__class__.__name__" is "Conflict"

  Scenario: The GitHub App signs in, and opens a branch and a pull request
    Given the GitHub App on recorded answers, with OPP-10 holding "old" on main
    When the app proposes OPP-10 by "david", from "old" to "new"
    Then the result is "https://github.com/Sustenaut/business-plan/pull/9"

  Scenario: The GitHub App's branch is the next one, from main, and its calls are logged
    Given the GitHub App on recorded answers, with OPP-10 holding "old" on main
    When the app proposes OPP-10 by "david", from "old" to "new"
    And what the app wrote to GitHub and logged is read
    Then the result's "writes.0" is "{"method": "POST", "path": "/git/refs", "body": {"ref": "refs/heads/opportunity/OPP-10-david-2", "sha": "base"}}"
    And the result's "writes.1.method" is "PUT"
    And the result's "writes.1.path" is "/contents/opportunities/OPP-10.md"
    And the result's "writes.1.body.sha" is "blob"
    And the result's "token" is "inst-token"
    And the result's "plugins" is "["github.app-token", "github.edit-pr"]"
    And the result's "repos" is "["opportunity-site"]"

  Scenario: Without a storage address the call log stays in the pod
    Given the environment does not set "OPPORTUNITY_CALL_LOG_URL"
    When the call log is made from the environment
    Then the result is empty

  Scenario: The call log goes to storage when the deployment says where it is
    Given the environment sets "OPPORTUNITY_CALL_LOG_URL" to "https://storage.example"
    And a file "token" holding "pod-token"
    And the environment sets "OPPORTUNITY_STORAGE_TOKEN_FILE" to "token"
    And the environment sets "HOSTNAME" to "app-7"
    And the storage sink's reports don't start
    When the call log is made from the environment
    Then the result's "class" is "StorageSink"
    And the result's "made once" is "true"
    And the result's "datasets" is "{"opportunity-site": "calls_opportunity_site"}"
    And the result's "sender" is "app-7"
    And the result's "token" is "pod-token"
    And the result's "base" is "https://storage.example"
