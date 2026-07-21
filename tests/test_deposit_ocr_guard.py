import unittest
from unittest.mock import patch

import deposit_ocr_guard as guard


class DepositOcrGuardTests(unittest.TestCase):
    def test_extracts_standard_utr_and_amount(self):
        result = guard._extract_payment_text("Payment successful Amount ₹1,250.50 UPI Ref 123456789012")
        self.assertEqual(result["utr"], "123456789012")
        self.assertEqual(result["amount"], 1250.50)
        self.assertEqual(result["status"], "success")

    def test_extracts_paytm_transaction_id_before_other_numbers(self):
        result = guard._extract_payment_text("Paid Rs 500 Txn ID 20212345678901234")
        self.assertEqual(result["utr"], "20212345678901234")
        self.assertEqual(result["amount"], 500)

    def test_formats_direct_vpa_and_mobile_fallback(self):
        self.assertEqual(guard._format_withdrawal_vpa(" User.Name@PayTM "), "user.name@paytm")
        with patch.dict(guard.os.environ, {"TITAN_MOBILE_UPI_HANDLE": "ybl"}):
            self.assertEqual(guard._format_withdrawal_vpa("+91 98765 43210"), "9876543210@ybl")

    @unittest.skipIf(guard.cv2 is None or guard.np is None, "OpenCV unavailable")
    def test_preprocessing_returns_binary_grayscale_image(self):
        image = guard.np.full((80, 240, 3), 35, dtype=guard.np.uint8)
        guard.cv2.putText(image, "123456789012", (3, 45), guard.cv2.FONT_HERSHEY_SIMPLEX, .55, (230, 230, 230), 1)
        ok, encoded = guard.cv2.imencode(".png", image)
        self.assertTrue(ok)
        output = guard._prepare_ocr_image(encoded.tobytes())
        self.assertEqual(len(output.shape), 2)
        self.assertTrue(set(guard.np.unique(output)).issubset({0, 255}))


if __name__ == "__main__":
    unittest.main()
