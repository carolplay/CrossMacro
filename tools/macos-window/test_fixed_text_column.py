import unittest
import window_macro as macro


class FixedColumnTests(unittest.TestCase):
    def test_header_width_does_not_move_arrow_column(self):
        target = {'text': '科技研究', 'bounds': [100, 270, 390, 740],
                  'exact': False, 'fixed_x': 432, 'offset': [0, 50]}
        for center in (163, 187):
            data = {'lines': [{'text': '科技研究', 'confidence': 1,
                              'bounds': [(center-40)/788, 646/1079, 80/788, 20/1079]}]}
            self.assertEqual(macro.text_target_points(data, target, [788, 1079], [0, 0], [788, 1079]), [[432, 706]])

    def test_fixed_column_preserves_label_bounds(self):
        target = {'text': '科技研究', 'bounds': [100, 270, 390, 740], 'fixed_x': 432}
        data = {'lines': [{'text': '科技研究', 'confidence': 1, 'bounds': [.7, .6, .1, .02]}]}
        self.assertEqual(macro.text_target_points(data, target, [788, 1079], [0, 0], [788, 1079]), [])

    def test_invalid_columns_rejected_before_input(self):
        for value in (-1, 788, True, '432'):
            flow = {'reference_size': [788, 1079], 'steps': [{'name': 'arrow', 'action': 'click',
                    'text_target': {'text': '科技研究', 'bounds': [100, 270, 390, 740], 'fixed_x': value},
                    'before': ['科技研究'], 'after': ['英雄']}]}
            with self.assertRaises(ValueError):
                macro.validate_workflow(flow)


if __name__ == '__main__':
    unittest.main()
