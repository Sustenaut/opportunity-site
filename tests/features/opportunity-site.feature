Feature: The opportunity site: reading, comments and reviews
  On a git checkout of fixture cards and a stand-in card format (fixtures/business-plan/) in
  the scratch directory, the in-memory store and a fake GitHub, signed in as the dev user.

  Background:
    Given a scratch directory
    And a file "." copied from "tests/fixtures/business-plan"
    And a git repository
    And everything is committed with the message "cards"
    And the site shows this checkout, on a laptop
    And the environment sets "OPPORTUNITY_DEV_USER" to "reviewer@example.org"

  Scenario: The index lists every card, ranked by expected levels per 100 h
    When I GET "/"
    Then the answer is 200
    And the answer includes "Expected levels per 100 h"
    And the answer includes "Example market report"
    And the answer includes "/c/OPP-01"" before "/c/OPP-10""
    And the answer includes "/c/OPP-10"" before "/c/OPP-02""

  Scenario: The index filters by kind
    When I GET "/?kind=platform"
    Then the answer includes "/c/OPP-01""
    And the answer includes "/c/OPP-10""
    And the answer does not include "/c/OPP-02""

  Scenario: A card's page shows its fields, its body and its reports
    When I GET "/c/OPP-01"
    Then the answer is 200
    And the answer includes "Example platform work"
    And the answer includes "data-anchor="f:kill_point""
    And the answer includes "/r/example-market"

  Scenario: A card that isn't there is 404
    When I GET "/c/OPP-99"
    Then the answer is 404

  Scenario: A report's page has its sections and the cards it names
    When I GET "/r/example-market"
    Then the answer is 200
    And the answer includes "data-anchor="s:verdict""
    And the answer includes "/c/OPP-01"

  Scenario: Card HTML is shown as text, and script links are dropped
    When the Markdown is rendered:
      """
      ## Plan

      <script>alert(1)</script> [x](javascript:alert(1)) [ok](https://a.eu)
      """
    Then the result is:
      """
      <h2 id="plan">Plan</h2>
      <p>&lt;script&gt;alert(1)&lt;/script&gt; <a>x</a> <a href="https://a.eu">ok</a></p>
      """

  Scenario: A card's sections are its headings, each an anchor
    When the Markdown's sections are listed:
      """
      ## Plan

      <script>alert(1)</script> [x](javascript:alert(1)) [ok](https://a.eu)
      """
    Then the result is "[["s:plan", "Plan"]]"

  Scenario: A comment on a field keeps its field, the commit shown and its author
    Given requests come from "http://testserver"
    When I comment "Why March?" on "f:kill_point" of "/c/OPP-10/comments", on the commit shown
    And the comments on "OPP-10" are read
    Then the answer is 303
    And the answer redirects to "/c/OPP-10#c1"
    And the result is:
      | id | anchor       | commit | author_email         | parent_id | resolved_by |
      | 1  | f:kill_point | shown  | reviewer@example.org | null      | null        |

  Scenario: A reply is on its thread, not on an anchor of its own
    Given "reviewer@example.org" commented "Why March?" on "f:kill_point" of "OPP-10"
    And the environment sets "OPPORTUNITY_DEV_USER" to "other@example.org"
    And requests come from "http://testserver"
    When I POST to "/c/OPP-10/comments" with the form:
      | field  | value        |
      | parent | 1            |
      | body   | The sandbox. |
      | anchor | s:x          |
    And the comments on "OPP-10" are read
    Then the answer is 303
    And the answer redirects to "/c/OPP-10#c1"
    And the result is:
      | id | anchor       | author_email         | parent_id |
      | 1  | f:kill_point | reviewer@example.org | null      |
      | 2  |              | other@example.org    | 1         |

  Scenario: A reply to no thread is 404
    Given requests come from "http://testserver"
    When I POST to "/c/OPP-10/comments" with the form:
      | field  | value |
      | parent | 7     |
      | body   | Hm.   |
    Then the answer is 404

  Scenario: A card's page shows its threads, on the version shown
    Given "reviewer@example.org" commented "Why March?" on "f:kill_point" of "OPP-10"
    And "other@example.org" replied "The sandbox." to thread 1
    When I GET "/c/OPP-10"
    Then the answer includes "Field: kill_point"
    And the answer includes "The sandbox."
    And the answer does not include "on an older version"

  Scenario: Only a thread's author may resolve it
    Given "reviewer@example.org" commented "Why March?" on "f:kill_point" of "OPP-10"
    And the environment sets "OPPORTUNITY_DEV_USER" to "other@example.org"
    And requests come from "http://testserver"
    When I send "POST" to "/comments/1/resolve"
    Then the answer is 403

  Scenario: A reply isn't a thread to resolve
    Given "reviewer@example.org" commented "Why March?" on "f:kill_point" of "OPP-10"
    And "other@example.org" replied "The sandbox." to thread 1
    And requests come from "http://testserver"
    When I send "POST" to "/comments/2/resolve"
    Then the answer is 404

  Scenario: A controller is named as one
    Given the environment sets "OPPORTUNITY_DEV_USER" to "owner@example.org"
    And the environment sets "OPPORTUNITY_DEV_GROUPS" to "controller,opportunity"
    When I GET "/c/OPP-10"
    Then the answer includes "· controller"

  Scenario: A controller may resolve any thread, which leaves the card nothing open
    Given "reviewer@example.org" commented "Why March?" on "f:kill_point" of "OPP-10"
    And "other@example.org" replied "The sandbox." to thread 1
    And the environment sets "OPPORTUNITY_DEV_USER" to "owner@example.org"
    And the environment sets "OPPORTUNITY_DEV_GROUPS" to "controller,opportunity"
    And requests come from "http://testserver"
    When I send "POST" to "/comments/1/resolve"
    And the comments on "OPP-10" are read
    Then the answer is 303
    And the answer redirects to "/c/OPP-10#c1"
    And the result's "0.resolved_by" is "owner@example.org"

  Scenario: A resolved thread is not counted
    Given "reviewer@example.org" commented "Why March?" on "f:kill_point" of "OPP-10"
    And "owner@example.org" resolved thread 1
    When the open threads and reviews are counted
    Then the result is empty

  Scenario: An empty comment is refused
    Given requests come from "http://testserver"
    When I POST to "/r/example-market/comments" with the form:
      | field | value |
      | body  |       |
    And the comments on "research/example-market" are read
    Then the answer is 422
    And the answer includes "Write something before posting."
    And the result is empty

  Scenario: The author resolves their own thread on a report
    Given requests come from "http://testserver"
    When I POST to "/r/example-market/comments" with the form:
      | field  | value     |
      | anchor | s:verdict |
      | body   | Sizes?    |
    And I send "POST" to "/comments/1/resolve"
    And the comments on "research/example-market" are read
    Then the answer is 303
    And the answer redirects to "/r/example-market#c1"
    And the result is:
      | anchor    | author_email         | resolved_by          |
      | s:verdict | reviewer@example.org | reviewer@example.org |

  Scenario: A post with no Origin is refused
    When I POST to "/c/OPP-10/comments" with the form:
      | field | value |
      | body  | hi    |
    And the comments on "OPP-10" are read
    Then the answer is 403
    And the result is empty

  Scenario: A post from another site is refused
    Given requests come from "https://evil.example"
    When I POST to "/c/OPP-10/comments" with the form:
      | field | value |
      | body  | hi    |
    And the comments on "OPP-10" are read
    Then the answer is 403
    And the result is empty

  Scenario: Reviews on the version shown say nothing of an older one
    Given "reviewer@example.org" reviewed "OPP-10" as "concerns", saying "Timing.", on the commit shown
    When I GET "/c/OPP-10"
    Then the answer includes "Reviewed with concerns"
    And the answer does not include "on an older version"

  Scenario: A review says when its card has changed since
    Given "reviewer@example.org" reviewed "OPP-10" as "concerns", saying "Timing.", on the commit shown
    And a file "opportunities/OPP-10.md" holding:
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

      One more line.
      """
    And everything is committed with the message "edit OPP-10"
    When I GET "/c/OPP-10"
    Then the answer includes "Reviewed with concerns"
    And the answer includes "on an older version"

  Scenario: A review of a report that didn't change stays on the version shown
    Given "reviewer@example.org" reviewed "research/example-market" as "reviewed", on the commit shown
    And a file "notes.txt" holding "a change elsewhere"
    And everything is committed with the message "a change elsewhere"
    When I GET "/r/example-market"
    Then the answer includes "Reviewed"
    And the answer does not include "on an older version"

  Scenario: A review is kept with the commit it was made on
    Given requests come from "http://testserver"
    When I review "/c/OPP-10/reviews" as "concerns", on the commit shown
    And the reviews on "OPP-10" are read
    Then the answer is 303
    And the answer redirects to "/c/OPP-10#reviews"
    And the result is:
      | verdict  | author_email         |
      | concerns | reviewer@example.org |

  Scenario: A verdict that isn't one is refused
    Given requests come from "http://testserver"
    When I review "/c/OPP-10/reviews" as "maybe", on the commit shown
    And the reviews on "OPP-10" are read
    Then the answer is 422
    And the answer includes "Pick a verdict, and keep the note under 500 characters."
    And the result is empty

  Scenario: A note of more than 500 characters is refused
    Given requests come from "http://testserver"
    When I review "/c/OPP-10/reviews" as "reviewed", with a note of 501 characters
    And the reviews on "OPP-10" are read
    Then the answer is 422
    And the result is empty
