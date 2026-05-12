import unittest

from app.domain.errors import ParseError
from app.domain.statuses import RegistrationStatus
from app.portal.parser import parse_login_form, parse_registration_response


class ParserTests(unittest.TestCase):
    def test_parse_login_form_hidden_inputs(self):
        html = """
        <html><body>
          <form>
            <input type="hidden" name="__RequestVerificationToken" value="abc">
            <input type="text" name="username">
          </form>
        </body></html>
        """

        fields = parse_login_form(html)

        self.assertEqual(fields["__RequestVerificationToken"], "abc")

    def test_parse_login_form_without_hidden_inputs_fails(self):
        with self.assertRaises(ParseError):
            parse_login_form("<html><form></form></html>")

    def test_parse_registration_success_json(self):
        result = parse_registration_response(200, '{"success": true, "message": "ok"}')

        self.assertEqual(result.status, RegistrationStatus.SUCCESS)

    def test_parse_registration_dnn_success_json(self):
        result = parse_registration_response(
            200,
            '{"Status":"OK","Results":"Success","Message":"","StackTrace":null}',
        )

        self.assertEqual(result.status, RegistrationStatus.SUCCESS)

    def test_parse_registration_already_registered(self):
        result = parse_registration_response(200, '{"message": "Da dang ky truoc do"}')

        self.assertEqual(result.status, RegistrationStatus.ALREADY_REGISTERED)

    def test_parse_registration_failed_text_not_success(self):
        result = parse_registration_response(200, '{"message": "Dang ky khong thanh cong"}')

        self.assertEqual(result.status, RegistrationStatus.FAILED)

    def test_parse_registration_login_page(self):
        result = parse_registration_response(
            200,
            "<html><form><input type='password' name='password'>Login</form></html>",
        )

        self.assertEqual(result.status, RegistrationStatus.NEED_RELOGIN)

    def test_parse_registration_invalid_json(self):
        result = parse_registration_response(200, "not-json")

        self.assertEqual(result.status, RegistrationStatus.PARSE_ERROR)

    def test_parse_registration_http_errors(self):
        self.assertEqual(
            parse_registration_response(429, "{}").status,
            RegistrationStatus.RATE_LIMITED,
        )
        self.assertEqual(
            parse_registration_response(500, "{}").status,
            RegistrationStatus.HTTP_ERROR,
        )


if __name__ == "__main__":
    unittest.main()
