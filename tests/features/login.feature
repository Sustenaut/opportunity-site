Feature: Signing in through the proxy
  oauth2-proxy passes the verified email and the access token; on each request the site asks
  the team realm (here a fake "keycloak" service, asked for its hash on every request) whether
  the person's access has changed, and does a full check at userinfo only when it has.

  Background:
    Given a scratch directory
    And a file "." copied from "tests/fixtures/business-plan"
    And a git repository
    And everything is committed with the message "cards"
    And the site shows this checkout, on a laptop
    And the environment does not set "OPPORTUNITY_DEV_USER"
    And the team realm is the fake "keycloak" service, asked on each request

  Scenario: Nobody signed in is 401
    When I GET "/"
    Then the answer is 401

  Scenario: Another service's role is 403
    Given the "keycloak" service answers "GET /realms/team/app-registration/sustenaut.eu/access-state" with 200 and:
      """
      {"hash": "one"}
      """
    And the "keycloak" service answers "GET /realms/team/protocol/openid-connect/userinfo" with 200 and:
      """
      {"access": ["release"]}
      """
    And I am signed in as "other@example.org"
    And requests carry the header "X-Forwarded-Access-Token" set to "other"
    When I GET "/"
    Then the answer is 403
    And the "keycloak" service was asked "GET /realms/team/protocol/openid-connect/userinfo" with the header "Authorization" set to "Bearer other"

  Scenario: A member reads, whatever the case of their email, and is no controller
    Given the "keycloak" service answers "GET /realms/team/app-registration/sustenaut.eu/access-state" with 200 and:
      """
      {"hash": "one"}
      """
    And the "keycloak" service answers "GET /realms/team/protocol/openid-connect/userinfo" with 200 and:
      """
      {"access": ["opportunity"]}
      """
    And I am signed in as "REVIEWER@EXAMPLE.ORG"
    And requests carry the header "X-Forwarded-Access-Token" set to "me"
    When I GET "/"
    Then the answer is 200
    And the answer does not include "· controller"

  Scenario: A controller is named as one
    Given the "keycloak" service answers "GET /realms/team/app-registration/sustenaut.eu/access-state" with 200 and:
      """
      {"hash": "one"}
      """
    And the "keycloak" service answers "GET /realms/team/protocol/openid-connect/userinfo" with 200 and:
      """
      {"access": ["controller", "opportunity"]}
      """
    And I am signed in as "owner@example.org"
    And requests carry the header "X-Forwarded-Access-Token" set to "boss"
    When I GET "/"
    Then the answer is 200
    And the answer includes "· controller"

  Scenario: A header the proxy passes through is never trusted
    Given requests carry the header "X-Auth-Request-Email" set to "reviewer@example.org"
    When I GET "/"
    Then the answer is 401

  Scenario: A forged groups header changes nothing: roles come from userinfo
    Given the "keycloak" service answers "GET /realms/team/app-registration/sustenaut.eu/access-state" with 200 and:
      """
      {"hash": "one"}
      """
    And the "keycloak" service answers "GET /realms/team/protocol/openid-connect/userinfo" with 200 and:
      """
      {"access": ["opportunity"]}
      """
    And I am signed in as "reviewer@example.org"
    And requests carry the header "X-Forwarded-Access-Token" set to "me"
    And requests carry the header "X-Forwarded-Groups" set to "controller,opportunity"
    When I GET "/"
    Then the answer is 200
    And the answer does not include "· controller"

  Scenario: Nothing changed needs no full check
    Given the "keycloak" service answers "GET /realms/team/app-registration/sustenaut.eu/access-state" with 200 and:
      """
      {"hash": "one"}
      """
    And the "keycloak" service answers "GET /realms/team/protocol/openid-connect/userinfo" with 200 and:
      """
      {"access": ["opportunity"]}
      """
    And I am signed in as "reviewer@example.org"
    And requests carry the header "X-Forwarded-Access-Token" set to "me"
    When I GET "/"
    And I GET "/"
    Then the answer is 200
    And the "keycloak" service was asked "GET /realms/team/app-registration/sustenaut.eu/access-state" 2 times
    And the "keycloak" service was asked "GET /realms/team/protocol/openid-connect/userinfo" 1 times

  Scenario: A role taken away is refused at the next request
    Given the "keycloak" service answers "GET /realms/team/app-registration/sustenaut.eu/access-state" with 200 and:
      """
      {"hash": "one"}
      """
    And the "keycloak" service answers "GET /realms/team/app-registration/sustenaut.eu/access-state" with 200 and:
      """
      {"hash": "two"}
      """
    And the "keycloak" service answers "GET /realms/team/protocol/openid-connect/userinfo" with 200 and:
      """
      {"access": ["opportunity"]}
      """
    And the "keycloak" service answers "GET /realms/team/protocol/openid-connect/userinfo" with 200 and:
      """
      {"access": ["plan"]}
      """
    And I am signed in as "reviewer@example.org"
    And requests carry the header "X-Forwarded-Access-Token" set to "me"
    When I GET "/"
    And I GET "/"
    Then the answer is 403
    And the "keycloak" service was asked "GET /realms/team/protocol/openid-connect/userinfo" 2 times

  Scenario: A role given back is let in at the next request
    Given the "keycloak" service answers "GET /realms/team/app-registration/sustenaut.eu/access-state" with 200 and:
      """
      {"hash": "two"}
      """
    And the "keycloak" service answers "GET /realms/team/app-registration/sustenaut.eu/access-state" with 200 and:
      """
      {"hash": "three"}
      """
    And the "keycloak" service answers "GET /realms/team/protocol/openid-connect/userinfo" with 200 and:
      """
      {"access": ["plan"]}
      """
    And the "keycloak" service answers "GET /realms/team/protocol/openid-connect/userinfo" with 200 and:
      """
      {"access": ["opportunity"]}
      """
    And I am signed in as "reviewer@example.org"
    And requests carry the header "X-Forwarded-Access-Token" set to "me"
    When I GET "/"
    And I GET "/"
    Then the answer is 200

  Scenario: Reading goes on while the realm can't be reached
    Given the "keycloak" service answers "GET /realms/team/app-registration/sustenaut.eu/access-state" with 200 and:
      """
      {"hash": "one"}
      """
    And the "keycloak" service answers "GET /realms/team/app-registration/sustenaut.eu/access-state" with 503
    And the "keycloak" service answers "GET /realms/team/protocol/openid-connect/userinfo" with 200 and:
      """
      {"access": ["opportunity"]}
      """
    And I am signed in as "reviewer@example.org"
    And requests carry the header "X-Forwarded-Access-Token" set to "me"
    When I GET "/"
    And I GET "/"
    Then the answer is 200

  Scenario: Changes are refused while the realm can't be reached
    Given the "keycloak" service answers "GET /realms/team/app-registration/sustenaut.eu/access-state" with 200 and:
      """
      {"hash": "one"}
      """
    And the "keycloak" service answers "GET /realms/team/app-registration/sustenaut.eu/access-state" with 503
    And the "keycloak" service answers "GET /realms/team/protocol/openid-connect/userinfo" with 200 and:
      """
      {"access": ["opportunity"]}
      """
    And I am signed in as "reviewer@example.org"
    And requests carry the header "X-Forwarded-Access-Token" set to "me"
    And requests come from "http://testserver"
    When I GET "/"
    And I send "POST" to "/comments/999/resolve"
    Then the answer is 503

  Scenario: Nobody can vouch for someone new while the realm can't be reached
    Given the "keycloak" service answers "GET /realms/team/app-registration/sustenaut.eu/access-state" with 503
    And I am signed in as "other@example.org"
    And requests carry the header "X-Forwarded-Access-Token" set to "new"
    When I GET "/"
    Then the answer is 503
    And the "keycloak" service was asked "GET /realms/team/protocol/openid-connect/userinfo" 0 times

  Scenario: Someone removed from all is sent to sign in again
    Given the "keycloak" service answers "GET /realms/team/app-registration/sustenaut.eu/access-state" with 200 and:
      """
      {"hash": "one"}
      """
    And the "keycloak" service answers "GET /realms/team/app-registration/sustenaut.eu/access-state" with 200 and:
      """
      {"hash": "four"}
      """
    And the "keycloak" service answers "GET /realms/team/protocol/openid-connect/userinfo" with 200 and:
      """
      {"access": ["opportunity"]}
      """
    And the "keycloak" service answers "GET /realms/team/protocol/openid-connect/userinfo" with 401
    And I am signed in as "reviewer@example.org"
    And requests carry the header "X-Forwarded-Access-Token" set to "me"
    When I GET "/"
    And I GET "/"
    Then the answer is 303
    And the answer redirects to "/oauth2/start?rd=/"

  Scenario: A change from someone removed from all is 401, keeping their page
    Given the "keycloak" service answers "GET /realms/team/app-registration/sustenaut.eu/access-state" with 200 and:
      """
      {"hash": "one"}
      """
    And the "keycloak" service answers "GET /realms/team/app-registration/sustenaut.eu/access-state" with 200 and:
      """
      {"hash": "four"}
      """
    And the "keycloak" service answers "GET /realms/team/protocol/openid-connect/userinfo" with 200 and:
      """
      {"access": ["opportunity"]}
      """
    And the "keycloak" service answers "GET /realms/team/protocol/openid-connect/userinfo" with 401
    And I am signed in as "reviewer@example.org"
    And requests carry the header "X-Forwarded-Access-Token" set to "me"
    And requests come from "http://testserver"
    When I GET "/"
    And I send "POST" to "/comments/999/resolve"
    Then the answer is 401

  Scenario: The wallet login isn't built yet, so it fails closed
    Given the environment sets "OPPORTUNITY_LOGIN" to "wallet"
    And I am signed in as "reviewer@example.org"
    When I GET "/"
    Then the answer is 500

  Scenario: The proxy login fails closed without the sign-in client
    Given the site's access check is not made yet
    And the environment does not set "OPPORTUNITY_CLIENT_ID"
    And the environment does not set "OPPORTUNITY_CLIENT_SECRET"
    And I am signed in as "reviewer@example.org"
    And requests carry the header "X-Forwarded-Access-Token" set to "me"
    When I GET "/"
    Then the answer is 500

  Scenario: The dev user is refused on a cluster
    Given the environment sets "OPPORTUNITY_DEV_USER" to "reviewer@example.org"
    And the environment sets "KUBERNETES_SERVICE_HOST" to "10.0.0.1"
    When I GET "/"
    Then the answer is 401
