import unittest

from src.portfolio_analysis_app.data_retrival import extract_holdings_csv_url


class DataRetrivalTests(unittest.TestCase):
    def test_extract_holdings_csv_url_joins_relative_ajax_links_without_query_leakage(self) -> None:
        product_page_url = (
            "https://www.ishares.com/uk/individual/en/products/251882/"
            "ishares-msci-world-ucits-etf-acc-fund?siteEntryPassthrough=true"
        )
        rendered_html = """
        <html>
          <body>
            <a href="/uk/individual/en/products/251882/ishares-msci-world-ucits-etf-acc-fund/1506575576011.ajax?fileType=csv&amp;fileName=SWDA_holdings&amp;dataType=fund">
              Download holdings
            </a>
          </body>
        </html>
        """

        csv_url = extract_holdings_csv_url(product_page_url, rendered_html)

        self.assertEqual(
            csv_url,
            "https://www.ishares.com/uk/individual/en/products/251882/"
            "ishares-msci-world-ucits-etf-acc-fund/1506575576011.ajax"
            "?fileType=csv&fileName=SWDA_holdings&dataType=fund",
        )
