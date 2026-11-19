Feature: Files on a card or a report
  Attachments and client documents are kept in storage, never in git: the site has the
  upload form once the deployment says where storage is, and reads a file back as a download.

  Background:
    Given a scratch directory
    And a file "." copied from "tests/fixtures/business-plan"
    And a git repository
    And everything is committed with the message "cards"
    And the site shows this checkout, on a laptop
    And the environment sets "OPPORTUNITY_DEV_USER" to "reviewer@example.org"
    And requests come from "http://testserver"

  Scenario: Without storage, files are off
    Given the environment does not set "OPPORTUNITY_FILES_URL"
    When the site's files are made from the environment
    Then the result is empty

  Scenario: Without storage, the upload button waits
    When I GET "/c/OPP-10"
    Then the answer includes "<button type="button" disabled>Upload a file</button>"

  Scenario: The same file again stays kept, and a changed one is a new file
    When "offer.pdf" is put in the fake files three times: as sent, again, and changed
    Then the result is:
      """
      {"again kept": true, "a new id for the change": true, "listed": 2}
      """

  Scenario: With uploads on, a card has the form
    Given the site's uploads are fake files
    When I GET "/c/OPP-10"
    Then the answer includes "<form method="post" action="/c/OPP-10/files" enctype="multipart/form-data">"
    And the answer does not include "disabled>Upload a file"

  Scenario: A file goes to its card, under a name storage takes, as it was sent
    Given the site's uploads are fake files
    And a file "offer.bin" of binary bytes and a stray multipart boundary
    When I upload "offer.bin" to "/c/OPP-10/files" as "OPP-10 offer (v1).pdf" of type "application/pdf", with:
      | field | value               |
      | label |  OPP-10 offer v1    |
      | kept  | on                  |
    And the files on "OPP-10" are read
    Then the answer is 303
    And the answer redirects to "/c/OPP-10#files"
    And the result is:
      | name                 | label           | kept | uploaded_by          | sha256 |
      | OPP-10-offer-v1-.pdf | OPP-10 offer v1 | true | reviewer@example.org | f5d6a0ded6b47a768491a2f7542a720192dc56ca413b36e3f5296adcb09bbd6a  |

  Scenario: A card's page lists its files
    Given the site's uploads are fake files
    And a file "offer.bin" of binary bytes and a stray multipart boundary
    When I upload "offer.bin" to "/c/OPP-10/files" as "OPP-10 offer (v1).pdf" of type "application/pdf", with:
      | field | value           |
      | label | OPP-10 offer v1 |
      | kept  | on              |
    And I GET "/c/OPP-10"
    Then the answer includes "OPP-10-offer-v1-.pdf"
    And the answer includes "OPP-10 offer v1"
    And the answer includes "kept"

  Scenario: A stored file is linked from its card
    Given the site's uploads are fake files
    And the fake files hold "chart.svg" for "OPP-10", holding "<svg onload=alert(1)></svg>"
    When I GET "/c/OPP-10"
    Then the answer includes "<a href="/files/a728dc7f64c76546ece3cdc3cc5f58dad886256a9d0af8c4a50b5fdb9bc24932/chart.svg">chart.svg</a>"

  Scenario: A stored file is read through the site, always as a download
    Given the site's uploads are fake files
    And the fake files hold "chart.svg" for "OPP-10", holding "<svg onload=alert(1)></svg>"
    When I GET "/files/a728dc7f64c76546ece3cdc3cc5f58dad886256a9d0af8c4a50b5fdb9bc24932/chart.svg"
    Then the answer is 200
    And the answer includes "<svg onload=alert(1)></svg>"
    And the answer's "content-disposition" is "attachment; filename="chart.svg""
    And the answer's "x-content-type-options" is "nosniff"
    And the answer's "cache-control" is "private, no-store"

  Scenario Outline: A file that isn't there is 404
    Given the site's uploads are fake files
    And the fake files hold "chart.svg" for "OPP-10", holding "<svg onload=alert(1)></svg>"
    When I GET "<path>"
    Then the answer is 404

    Examples:
      | path                                                                            |
      | /files/a728dc7f64c76546ece3cdc3cc5f58dad886256a9d0af8c4a50b5fdb9bc24932/other.svg |
      | /files/abc/chart.svg                                                            |
      | /files/a728dc7f64c76546ece3cdc3cc5f58dad886256a9d0af8c4a50b5fdb9bc24932/..%2Fx    |

  Scenario: A file storage doesn't give is 503
    Given the site's uploads don't answer
    When I GET "/files/a728dc7f64c76546ece3cdc3cc5f58dad886256a9d0af8c4a50b5fdb9bc24932/chart.svg"
    Then the answer is 503

  Scenario: With uploads off, no file is read
    Given the site's uploads are switched off
    When I GET "/files/a728dc7f64c76546ece3cdc3cc5f58dad886256a9d0af8c4a50b5fdb9bc24932/chart.svg"
    Then the answer is 404

  Scenario: A report's files are its research subject, not kept
    Given the site's uploads are fake files
    And a file "figure.png" holding "PNG"
    When I upload "figure.png" to "/r/example-market/files" as "figure.png" of type "image/png"
    And the files on "research/example-market" are read
    Then the answer is 303
    And the result's "0.kept" is "false"
    And the result has 1 file

  Scenario: An upload without a file says so
    Given the site's uploads are fake files
    When I upload no file to "/c/OPP-10/files"
    Then the answer is 422
    And the answer includes "Choose a file to upload."

  Scenario: An upload with a long label says so
    Given the site's uploads are fake files
    And a file "a.pdf" holding "%PDF"
    When I upload "a.pdf" to "/c/OPP-10/files" as "a.pdf" of type "application/pdf", labelled with 201 characters
    Then the answer is 422
    And the answer includes "under 200 characters"

  Scenario: Storage refusing a file is shown on the page
    Given the site's uploads refuse, saying "opportunity takes pdf, pptx, docx, png, jpg, svg, csv, xlsx, not .exe"
    And a file "a.exe" holding "MZ"
    When I upload "a.exe" to "/c/OPP-10/files" as "a.exe" of type "application/x"
    Then the answer is 422
    And the answer includes "Storage didn&#39;t take it: opportunity takes pdf"

  Scenario: Storage not answering is shown on the page
    Given the site's uploads don't answer
    And a file "a.pdf" holding "%PDF"
    When I upload "a.pdf" to "/c/OPP-10/files" as "a.pdf" of type "application/pdf"
    Then the answer is 503
    And the answer includes "Try again in a minute"

  Scenario: Uploads need storage switched on
    Given a file "a.pdf" holding "%PDF"
    When I upload "a.pdf" to "/c/OPP-10/files" as "a.pdf" of type "application/pdf"
    Then the answer is 404

  Scenario: Uploads come only from the site's own pages
    Given the site's uploads are fake files
    And requests come from "https://evil.example"
    And a file "a.pdf" holding "%PDF"
    When I upload "a.pdf" to "/c/OPP-10/files" as "a.pdf" of type "application/pdf"
    Then the answer is 403

  Scenario: An upload is a form
    Given the site's uploads are fake files
    When I POST to "/c/OPP-10/files" with the form:
      | field | value |
      | label | x     |
    Then the answer is 415

  Scenario: An upload to a card that isn't there is 404
    Given the site's uploads are fake files
    And a file "a.pdf" holding "%PDF"
    When I upload "a.pdf" to "/c/NOPE/files" as "a.pdf" of type "application/pdf"
    Then the answer is 404

  Scenario: A file larger than storage takes is 413
    Given the site's uploads are fake files
    And the site takes files of at most 10 bytes
    And a file "a.pdf" of 71680 bytes
    When I upload "a.pdf" to "/c/OPP-10/files" as "a.pdf" of type "application/pdf"
    Then the answer is 413

  Scenario Outline: A file's name is made one storage takes
    When the file name "<name>" is made one storage takes
    Then the result is "<safe>"

    Examples:
      | name                                  | safe                  |
      | C:\\Users\\me\\Market report (v3).pdf  | Market-report-v3-.pdf |
      | ../.hidden.txt                        | file.hidden.txt       |
      | ü.png                                 | file-.png             |

  Scenario: No name is "file"
    When no file name is made one storage takes
    Then the result is "file"

  Scenario: A long name is cut to 120, keeping its extension
    When a file name of 300 letters and .pdf is made one storage takes
    Then the result has 120 characters
    And the result matches "aaa*a.pdf"
