Feature: The opportunity site
  On a git checkout of fixture cards and a stand-in card format (fixtures/business-plan/) made in a temporary folder, the in-memory store, and a fake GitHub. The PostgreSQL store runs too when OPPORTUNITY_TEST_DATABASE_URL names an empty database.

  Scenario: Index lists every card ranked and filters by kind
    Then index lists every card ranked and filters by kind

  Scenario: Card page shows fields body and its reports
    Then card page shows fields body and its reports

  Scenario: Card HTML is shown as text and script links are dropped
    Then card HTML is shown as text and script links are dropped

  Scenario: Comment on a field reply and resolve
    Then comment on a field reply and resolve

  Scenario: Author resolves own thread and empty comments are refused
    Then author resolves own thread and empty comments are refused

  Scenario: Posts from elsewhere are refused
    Then posts from elsewhere are refused

  Scenario: Reviews say when they are on an older version
    Then reviews say when they are on an older version

  Scenario: Front matter round trips for every card
    Then front matter round trips for every card

  Scenario: An edit opens a pull request naming the editor
    Then an edit opens a pull request naming the editor

  Scenario: Edits that do not read cleanly open nothing
    Then edits that do not read cleanly open nothing

  Scenario: A research report is added by pull request
    Then a research report is added by pull request

  Scenario: Branch names count up
    Then branch names count up

  Scenario: The github app signs in and opens a branch and pull request
    Then the github app signs in and opens a branch and pull request

  Scenario: The call log goes to storage only when the deployment says
    Then the call log goes to storage only when the deployment says

  Scenario: The checkout is pulled at most once a minute
    Then the checkout is pulled at most once a minute

  Scenario: The first request clones even soon after boot
    Then the first request clones even soon after boot

  Scenario: A broken card is reported not fatal
    Then a broken card is reported not fatal

  Scenario: The card format comes from the commit shown
    Then the card format comes from the commit shown

  Scenario: A broken format is reported and the last one stays
    Then a broken format is reported and the last one stays

  Scenario: Without a format the site says so
    Then without a format the site says so

  Scenario: The proxy login asks on each request
    Then the proxy login asks on each request

  Scenario: The proxy login fails closed without the client
    Then the proxy login fails closed without the client

  Scenario: The dev user is refused on a cluster
    Then the dev user is refused on a cluster

  Scenario: Files wait for storage
    Then files wait for storage

  Scenario: With uploads on a card has the form and a file goes to its subject
    Then with uploads on a card has the form and a file goes to its subject

  Scenario: A stored file is read through the site as a download
    Then a stored file is read through the site as a download

  Scenario: The client reads a file with the pod's token
    Then the client reads a file with the pod's token

  Scenario: A report's files are its research subject
    Then a report's files are its research subject

  Scenario: An upload without a file or with a long label says so
    Then an upload without a file or with a long label says so

  Scenario: Storage refusing or down is shown on the page
    Then storage refusing or down is shown on the page

  Scenario: Uploads need storage switched on the site's own page and a form
    Then uploads need storage switched on the site's own page and a form

  Scenario: A file's name is made one storage takes
    Then a file's name is made one storage takes

  Scenario: Storage saying no or not answering becomes the site's own errors
    Then storage saying no or not answering becomes the site's own errors

  Scenario: An upload goes to storage with its card as subject
    Then an upload goes to storage with its card as subject

  Scenario: A card's files are the tenant's listing for its subject
    Then a card's files are the tenant's listing for its subject

  Scenario: Storage refusing a listing is an error not an empty list
    Then storage refusing a listing is an error not an empty list

  Scenario: Files are on when the deployment says where storage is
    Then files are on when the deployment says where storage is

  Scenario: Postgres store
    Then postgres store

  Scenario: The site is alive and ready with its database
    Then the site is alive and ready with its database

  Scenario: A database it cannot reach makes it unready but not dead
    Then a database it cannot reach makes it unready but not dead

  Scenario: A store not made yet is checked from the environment
    Then a store not made yet is checked from the environment

  Scenario: The storage token is read from its file on each upload
    Then the storage token is read from its file on each upload
