Feature: The site's files in storage
  The private tenant opportunity in storage.sustenaut.eu, through integrations' storage client
  on recorded answers, read and written with the pod's token.

  Scenario: A file is read with the pod's token
    Given storage on recorded answers:
      """
      {"GET https://storage.sustenaut.eu/opportunity/f/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/a.pdf": {"status": 200, "text": "%PDF"}}
      """
    When the file "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" named "a.pdf" is read from storage
    And what was sent to storage and logged is read
    Then the result's "sent.0.authorization" is "Bearer pod-token"
    And the result's "sent.0.url" is "https://storage.sustenaut.eu/opportunity/f/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/a.pdf"

  Scenario: A file read is its bytes
    Given storage on recorded answers:
      """
      {"GET https://storage.sustenaut.eu/opportunity/f/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/a.pdf": {"status": 200, "text": "%PDF"}}
      """
    When the file "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" named "a.pdf" is read from storage
    Then the result is "%PDF"

  Scenario Outline: Storage not giving a file is the site's own error
    Given storage on recorded answers:
      """
      {"GET https://storage.sustenaut.eu/opportunity/f/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/a.pdf": <answer>}
      """
    When the file "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" named "a.pdf" is read from storage
    Then it is refused, saying "<message>"
    And the refusal's "__class__.__name__" is "<refusal>"

    Examples:
      | answer                                       | refusal     | message        |
      | {"status": 404, "json": {"error": "not found"}} | LookupError | aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/a.pdf |
      | {"status": 403, "json": {"error": "no"}}        | Refused     | no             |
      | {"error": "down"}                               | Unavailable | down           |

  Scenario: Storage saying no to a file is refused with its reason
    Given storage on recorded answers:
      """
      {"POST https://storage.sustenaut.eu/opportunity/files": {"status": 415, "json": {"error": "opportunity takes pdf, not .exe"}}}
      """
    When "a.exe" holding "MZ" is put in storage for "OPP-10", by "reviewer@example.org"
    Then it is refused, saying "opportunity takes pdf, not .exe"
    And the refusal's "__class__.__name__" is "Refused"

  Scenario: Storage not answering an upload is unavailable
    Given storage on recorded answers:
      """
      {}
      """
    When "a.pdf" holding "%PDF" is put in storage for "OPP-10", by "reviewer@example.org"
    Then it is refused
    And the refusal's "__class__.__name__" is "Unavailable"

  Scenario: An upload goes to storage with its card as subject
    Given storage on recorded answers:
      """
      {"POST https://storage.sustenaut.eu/opportunity/files": {"status": 200, "json": {"id": "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff", "name": "offer.pdf", "url": "/opportunity/f/ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff/offer.pdf", "type": "application/pdf", "size": 6, "label": "v1", "subject": "OPP-10", "kept": true}}}
      """
    When "offer.pdf" holding "%PDF-1" is put in storage for "OPP-10", by "reviewer@example.org", labelled "v1" and kept
    Then the result's "id" is "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
    And the result's "subject" is "OPP-10"
    And the result's "name" is "offer.pdf"
    And the result's "url" is "https://storage.sustenaut.eu/opportunity/f/ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff/offer.pdf"
    And the result's "type" is "application/pdf"
    And the result's "size" is "6"
    And the result's "label" is "v1"
    And the result's "kept" is "true"
    And the result's "uploaded_by" is "reviewer@example.org"

  Scenario: An upload's form names the file, its label, subject, whether kept, and for whom
    Given storage on recorded answers:
      """
      {"POST https://storage.sustenaut.eu/opportunity/files": {"status": 200, "json": {"id": "ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff", "name": "offer.pdf", "url": "/opportunity/f/ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff/offer.pdf", "type": "application/pdf", "size": 6, "label": "v1", "subject": "OPP-10", "kept": true}}}
      """
    When "offer.pdf" holding "%PDF-1" is put in storage for "OPP-10", by "reviewer@example.org", labelled "v1" and kept
    And what was sent to storage and logged is read
    Then the result's "sent.0.method" is "POST"
    And the result's "sent.0.url" is "https://storage.sustenaut.eu/opportunity/files"
    And the result's "sent.0.authorization" is "Bearer pod-token"
    And the result's "sent.0.form" is "{"file": "%PDF-1", "name": "offer.pdf", "label": "v1", "subject": "OPP-10", "kept": "true", "for": "reviewer@example.org"}"
    And the result's "records" is "[["storage.api", "write", "ok"]]"

  Scenario: A card's files are the tenant's listing for its subject, every page of it
    Given storage on recorded answers:
      """
      {"GET https://storage.sustenaut.eu/opportunity/list?prefix=f%2F": {"status": 200, "json": {"files": [
         {"name": "terms.pdf", "id": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", "url": "/opportunity/f/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb/terms.pdf", "size": 3, "uploaded": "2026-11-06T08:00:00.000Z", "metadata": {"subject": "OPP-10", "label": "v2", "kept": "true", "by": "k8s:opportunity/app", "for": "reviewer@example.org"}},
         {"name": "other.pdf", "id": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc", "url": "/opportunity/f/cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc/other.pdf", "size": 3, "uploaded": "2026-11-06T08:00:00.000Z", "metadata": {"subject": "OPP-11", "by": "k8s:opportunity/app"}}], "cursor": "2"}},
       "GET https://storage.sustenaut.eu/opportunity/list?prefix=f%2F&cursor=2": {"status": 200, "json": {"files": [
         {"name": "figure.png", "id": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "url": "/opportunity/f/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/figure.png", "size": 3, "uploaded": "2026-11-06T08:00:00.000Z", "metadata": {"subject": "OPP-10", "by": "k8s:opportunity/app"}},
         {"name": "old.pdf", "id": "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd", "url": "/opportunity/f/dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd/old.pdf", "size": 3, "uploaded": "2026-11-06T08:00:00.000Z", "metadata": {}}], "cursor": null}}}
      """
    When the files on "OPP-10" are listed from storage
    Then the result is:
      | name       | type            | label | kept  | uploaded_by          | url                                                       |
      | figure.png | image/png       |       | false | k8s:opportunity/app  | https://storage.sustenaut.eu/opportunity/f/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/figure.png |
      | terms.pdf  | application/pdf | v2    | true  | reviewer@example.org | https://storage.sustenaut.eu/opportunity/f/bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb/terms.pdf  |

  Scenario: Listing reads both pages with the pod's token
    Given storage on recorded answers:
      """
      {"GET https://storage.sustenaut.eu/opportunity/list?prefix=f%2F": {"status": 200, "json": {"files": [], "cursor": "2"}},
       "GET https://storage.sustenaut.eu/opportunity/list?prefix=f%2F&cursor=2": {"status": 200, "json": {"files": [], "cursor": null}}}
      """
    When the files on "OPP-10" are listed from storage
    And what was sent to storage and logged is read
    Then the result's "requests" is "2"
    And the result's "sent.0.authorization" is "Bearer pod-token"
    And the result's "sent.1.url" is "https://storage.sustenaut.eu/opportunity/list?prefix=f%2F&cursor=2"

  Scenario: Storage refusing a listing is an error, not an empty list
    Given storage on recorded answers:
      """
      {"GET https://storage.sustenaut.eu/opportunity/list?prefix=f%2F": {"status": 403, "json": {"error": "k8s:x may not read here"}}}
      """
    When the files on "OPP-10" are listed from storage
    Then it is refused, saying "HTTP 403 k8s:x may not read here"
    And the refusal's "__class__.__name__" is "StorageError"

  Scenario: Files are on when the deployment says where storage is
    Given a scratch directory
    And a file "token" holding "pod-token"
    And the environment sets "OPPORTUNITY_FILES_URL" to "https://storage.example/"
    And the environment sets "OPPORTUNITY_STORAGE_TOKEN_FILE" to "token"
    And the environment does not set "OPPORTUNITY_CALL_LOG_URL"
    When the site's files are made from the environment
    Then the result is:
      """
      {"class": "StorageFiles", "base_url": "https://storage.example", "tenant": "opportunity", "token": "pod-token", "repo": "opportunity-site"}
      """

  Scenario: The storage token is read from its file
    Given a scratch directory
    And a file "token" holding "first"
    When the storage token is read from its file
    Then the result is "first"

  Scenario: The storage token is read from its file again on each upload
    Given a scratch directory
    And a file "token" holding "first"
    And the storage token was read from its file
    When the file "token" changes to:
      """
      second
      """
    And the storage token is read from its file
    Then the result is "second"
