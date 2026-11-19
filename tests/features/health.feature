Feature: The site's health, and its PostgreSQL store
  /livez says the process runs; /healthz says it can reach what no page works without, its
  database. The PostgreSQL store runs when OPPORTUNITY_TEST_DATABASE_URL names an empty database.

  Scenario: The site is alive
    When I GET "/livez"
    Then the answer is 200
    And the answer is the JSON:
      """
      {"ok": true}
      """

  Scenario: The site is ready with its database
    When I GET "/healthz"
    Then the answer is 200
    And the answer is the JSON:
      """
      {"ok": true, "unhealthy": []}
      """

  Scenario: A database it can't reach makes it unready
    Given the site's database is down
    When I GET "/healthz"
    Then the answer is 503
    And the answer is the JSON:
      """
      {"ok": false, "unhealthy": ["opportunity.postgres"]}
      """

  Scenario: A database it can't reach leaves it alive
    Given the site's database is down
    When I GET "/livez"
    Then the answer is 200

  Scenario: A store not made yet is checked from the environment
    Given the environment sets "OPPORTUNITY_DATABASE_URL" to "host=127.0.0.1 port=1 dbname=none"
    When the store not made yet is checked
    Then the result is:
      """
      {"ok": false, "plugin": "opportunity.postgres"}
      """

  Scenario: A store not made yet, with no database named, is the in-memory one
    Given the environment does not set "OPPORTUNITY_DATABASE_URL"
    When the store not made yet is checked
    Then the result's "ok" is "true"

  Scenario: The PostgreSQL store migrates once
    Given an empty PostgreSQL database, from OPPORTUNITY_TEST_DATABASE_URL
    When the store is migrated twice
    Then the result is "[["001_comments_and_reviews.sql"], []]"

  Scenario: The PostgreSQL store keeps threads and reviews, and resolves only a thread's first comment
    Given an empty PostgreSQL database, from OPPORTUNITY_TEST_DATABASE_URL
    And the store is migrated
    When a thread with a reply and a review are kept, and both comments resolved by the controller
    Then the result is:
      """
      {"listed in order": true, "reply's parent": true, "tally before": {"OPP-10": [1, 1]},
       "tally after": {"OPP-10": [0, 1]}, "root resolved by": "owner@example.org", "reply resolved by": null,
       "review": "Not convinced"}
      """

  Scenario: The PostgreSQL store refuses a verdict that isn't one
    Given an empty PostgreSQL database, from OPPORTUNITY_TEST_DATABASE_URL
    And the store is migrated
    When a review "maybe" is kept
    Then it is refused
    And the refusal's "__class__.__name__" is "CheckViolation"
