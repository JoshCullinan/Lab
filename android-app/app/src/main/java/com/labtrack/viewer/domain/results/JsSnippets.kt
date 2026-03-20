package com.labtrack.viewer.domain.results

/**
 * JavaScript evaluation strings — verbatim port from core/results.py.
 * These are evaluated in the hidden WebView to scrape TrakCare DOM.
 */
object JsSnippets {

    /** Scrape patient search results table. Returns JSON array of patient hits. */
    val PARSE_SEARCH_RESULTS = """
        (function() {
            var rows = document.querySelectorAll('tr[id^="web_DEBDebtor_FindList_0-row-"]');
            return Array.from(rows).map(function(row, i) {
                function cellText(suffix) {
                    var el = row.querySelector('[id$="' + suffix + '"]');
                    return el ? el.innerText.trim() : '';
                }
                return {
                    row_index: i,
                    mrn: cellText('-item-MRN-link') || cellText('-item-MRN'),
                    surname: cellText('-item-Surname'),
                    given_name: cellText('-item-GivenName'),
                    dob: cellText('-item-DOB'),
                    episode: cellText('-item-Episode')
                };
            });
        })()
    """.trimIndent()

    /** Scrape episode list after clicking a patient. Returns JSON object with patient info + rows. */
    val SCRAPE_EPISODE_LIST = """
        (function() {
            function text(id) {
                var el = document.getElementById(id);
                return el ? el.innerText.trim() : '';
            }

            var surname   = text('web_EPVisitNumber_List_Banner-row-0-item-Surname');
            var givenName = text('web_EPVisitNumber_List_Banner-row-0-item-GivenName');
            var mrn       = text('web_EPVisitNumber_List_Banner-row-0-item-MRNLink-link');
            var episode   = text('web_EPVisitNumber_List_Banner-row-0-item-Episode');
            var dob       = text('web_EPVisitNumber_List_Banner-row-0-item-DOB');

            var allVistsLinks = Array.from(document.querySelectorAll('a[id^="VISTS_"]'))
                .map(function(a) { return {id: a.id, text: a.innerText.trim()}; });
            var clickableNames = new Set(allVistsLinks.map(function(l) { return l.text; }));

            var episodeTrs = document.querySelectorAll('tr[id^="web_EPVisitNumber_List_1-row-"]');
            var rows = Array.from(episodeTrs).map(function(tr, i) {
                var rowId = tr.id;
                var idMatch = rowId.match(/-row-(\d+)$/);
                var rowIndex = idMatch ? parseInt(idMatch[1]) : i;

                var doctor         = text(rowId + '-item-Doctor');
                var collectionDate = text(rowId + '-item-CollectionDate');
                var collectionTime = text(rowId + '-item-CollectionTime');
                var episodeNum     = text(rowId + '-item-Episode') || '';
                var pdfSelector    = '#' + rowId + '-item-DocRptPDF-link';

                var rowVistsLinks = Array.from(tr.querySelectorAll('a[id^="VISTS_"]'))
                    .map(function(a) { return {id: a.id, text: a.innerText.trim()}; });

                return {
                    row_index: rowIndex,
                    episode_number: episodeNum,
                    doctor: doctor,
                    collection_datetime: collectionDate + ' ' + collectionTime,
                    pdf_selector: pdfSelector,
                    clickable: rowVistsLinks,
                    pending: []
                };
            });

            var tsListLabel = document.querySelector('[id$="-item-TSList-label"]');
            var pending = [];
            if (tsListLabel) {
                var container = tsListLabel.closest('td') || tsListLabel.parentElement;
                if (container) {
                    var walker = document.createTreeWalker(
                        container, NodeFilter.SHOW_TEXT, null, false
                    );
                    var node;
                    while (node = walker.nextNode()) {
                        var t = node.textContent.trim();
                        if (t && t.length <= 10 && t !== 'Test Set List' && !clickableNames.has(t)) {
                            pending.push(t);
                        }
                    }
                }
            }

            var firstRow = rows[0] || {};

            return {
                patient_name: surname + ', ' + givenName,
                patient_id: mrn,
                episode: episode,
                dob: dob,
                doctor: firstRow.doctor || '',
                collection_datetime: firstRow.collection_datetime || '',
                clickable: allVistsLinks,
                pending: pending,
                rows: rows
            };
        })()
    """.trimIndent()

    /** Parse patient info from result detail page. */
    val PARSE_DETAIL = """
        (function() {
            function text(id) {
                var el = document.getElementById(id);
                return el ? el.innerText.trim() : '';
            }

            return {
                patient_name: text('web_EPVisitNumber_List_Banner-row-0-item-Surname')
                    + ', ' + text('web_EPVisitNumber_List_Banner-row-0-item-GivenName'),
                patient_id: text('web_EPVisitNumber_List_Banner-row-0-item-MRNLink-link'),
                episode: text('web_EPVisitNumber_List_Banner-row-0-item-Episode'),
                dob: text('web_EPVisitNumber_List_Banner-row-0-item-DOB'),
                requesting_doctor: text('web_EPVisitTestSet_Result_0-item-OrderedBy'),
                status: text('web_EPVisitTestSet_Result_0-item-VISTSStatusResult'),
                collection_datetime: text('web_EPVisitTestSet_Result_0-item-CollectionDate')
                    + ' ' + text('web_EPVisitTestSet_Result_0-item-CollectionTime'),
                result_datetime: text('web_EPVisitTestSet_Result_0-item-ResultDate')
                    + ' ' + text('web_EPVisitTestSet_Result_0-item-ResultTime')
            };
        })()
    """.trimIndent()

    /** Parse test result rows from the results table. */
    val PARSE_ROWS = """
        (function() {
            function text(id) {
                var el = document.getElementById(id);
                return el ? el.innerText.trim() : '';
            }

            var collectionDate = text('web_EPVisitTestSet_Result_0-item-CollectionDate');
            var collectionTime = text('web_EPVisitTestSet_Result_0-item-CollectionTime');

            var rows = document.querySelectorAll('tr[id^="web_EPVisitTestSet_Result_0-row-"]');
            var tests = [];
            rows.forEach(function(row) {
                var rowId = row.id;
                var testName = text(rowId + '-item-TestItem');
                var value    = text(rowId + '-item-Value');

                var flag = null;
                var statusEl = document.getElementById(rowId + '-item-Value-status');
                if (statusEl) {
                    var statusText = statusEl.innerText.trim();
                    if (statusText) flag = statusText;
                }
                if (!flag) {
                    var valueEl = document.getElementById(rowId + '-item-Value');
                    if (valueEl) {
                        var color = window.getComputedStyle(valueEl).color;
                        if (color === 'rgb(255, 0, 0)' || color === 'rgb(204, 0, 0)') {
                            flag = 'ABNORMAL';
                        }
                    }
                }

                var cells = row.querySelectorAll('td');
                var unit = '';
                var refRange = '';
                if (cells.length > 2) unit = cells[2] ? cells[2].innerText.trim() : '';
                if (cells.length > 3) refRange = cells[3] ? cells[3].innerText.trim() : '';

                if (testName) {
                    tests.push({
                        test_name: testName,
                        value: value,
                        unit: unit,
                        reference_range: refRange,
                        flag: flag,
                        collection_datetime: collectionDate + ' ' + collectionTime
                    });
                }
            });
            return tests;
        })()
    """.trimIndent()
}
