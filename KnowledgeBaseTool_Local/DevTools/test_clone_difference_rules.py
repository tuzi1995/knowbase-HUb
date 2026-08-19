import unittest

from clone_difference_rules import (
    merge_difference_rules,
    parse_manual_difference_text,
    validate_ai_difference_rules,
)


class CloneDifferenceRuleTests(unittest.TestCase):
    def test_labeled_model_clauses_are_split_into_correct_feature_rules(self):
        rules = parse_manual_difference_text(
            """# P30 Pro对比 P20 Ultra 活水版
P30 Pro：40000Pa大吸力，除尘、吸深层灰尘能力更强 P20 Ultra 活水版：22000Pa吸力
P30 Pro：60℃热力高温去渍 + 15N拖地压力，高温溶解油渍、酱料等顽固污渍 P20 Ultra 活水版：常温拖地，同样15N下压力，无热水拖地，只适合日常普通脏污
P30 Pro：16孔喷淋，出水更均匀、水量更大，滚筒浸润更充分，水洗效果更好 P20 Ultra 活水版：8孔喷淋，滚筒浸湿均匀
P30 Pro：支持超300+种物体识别 P20 Ultra 活水版：支持200种可识别障碍物
P30 Pro：8.98cm超薄机身，更薄，低矮床底、柜体通行优势更大 P20 Ultra 活水版：11.9cm机身
P30 Pro：最高8.8cm越障，常规4.5cm，门槛、厚脚垫轻松翻越 P20 Ultra 活水版：仅2cm越障
P30 Pro：6400mAh大容量电池，大户型续航更长 P20 Ultra 活水版：5200mAh电池""",
            target_model="P30 Pro",
        )

        by_feature = {rule["feature_id"]: rule for rule in rules}
        self.assertEqual(set(by_feature), {
            "max_suction",
            "hot_water_mopping",
            "spray_hole_count",
            "object_recognition_count",
            "body_height",
            "obstacle_crossing_height",
            "battery_capacity",
        })
        self.assertEqual((by_feature["max_suction"]["source_value"], by_feature["max_suction"]["target_value"]), ("22000Pa", "40000Pa"))
        self.assertEqual((by_feature["hot_water_mopping"]["source_value"], by_feature["hot_water_mopping"]["target_value"]), ("常温拖地", "60℃热力高温"))
        self.assertEqual((by_feature["spray_hole_count"]["source_value"], by_feature["spray_hole_count"]["target_value"]), ("8孔", "16孔"))
        self.assertEqual((by_feature["object_recognition_count"]["source_value"], by_feature["object_recognition_count"]["target_value"]), ("200种", "300+种"))
        self.assertNotIn("mop_pressure", by_feature)

    def test_numeric_difference_is_traceable_to_user_text(self):
        rules = parse_manual_difference_text(
            "旧型号最大吸力 22000Pa，新品 40000Pa",
            target_model="P30 Pro",
        )

        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0]["feature_id"], "max_suction")
        self.assertEqual(rules[0]["source_value"], "22000Pa")
        self.assertEqual(rules[0]["target_value"], "40000Pa")
        self.assertEqual(rules[0]["status"], "needs_confirmation")
        self.assertIn("22000Pa", rules[0]["evidence_quote"])

    def test_removed_feature_is_parsed_as_boolean_difference(self):
        rules = parse_manual_difference_text(
            "A30 Pro Ultra 3.0机身颜色为净静土棕，取消脏污检测功能",
            target_model="A30 Pro Ultra 3.0",
        )

        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0]["feature_id"], "dirt_detection")
        self.assertEqual(rules[0]["feature_name"], "脏污检测")
        self.assertEqual(rules[0]["source_value"], "支持")
        self.assertEqual(rules[0]["target_value"], "不支持")
        self.assertEqual(rules[0]["evidence_quote"], "A30 Pro Ultra 3.0机身颜色为净静土棕，取消脏污检测功能")

    def test_reordered_removed_feature_maps_to_canonical_feature(self):
        rules = parse_manual_difference_text(
            "A30 Pro Ultra 3.0取消检测脏污功能",
            target_model="A30 Pro Ultra 3.0",
        )

        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0]["feature_id"], "dirt_detection")
        self.assertEqual(rules[0]["feature_name"], "脏污检测")

    def test_added_feature_is_parsed_without_ai(self):
        rules = parse_manual_difference_text(
            "P30 Pro新增边刷抬升功能",
            target_model="P30 Pro",
        )

        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0]["feature_name"], "边刷抬升")
        self.assertEqual(rules[0]["source_value"], "不支持")
        self.assertEqual(rules[0]["target_value"], "支持")

    def test_current_input_keeps_model_direction_and_paired_boolean_feature(self):
        rules = parse_manual_difference_text(
            """吸力升级：A30 Pro Ultra 3.0为32000Pa，A30 Pro Ultra为25000Pa。
抗菌除臭：A30 Pro Ultra 3.0支持一次性滤网；A30 Pro Ultra不支持。
A30 Pro Ultra 3.0机身颜色为净静土棕，取消脏污检测功能""",
            target_model="A30 Pro Ultra 3.0",
        )

        by_feature = {rule["feature_name"]: rule for rule in rules}
        self.assertEqual((
            by_feature["最大吸力"]["source_value"],
            by_feature["最大吸力"]["target_value"],
        ), ("25000Pa", "32000Pa"))
        self.assertEqual((
            by_feature["一次性滤网"]["source_value"],
            by_feature["一次性滤网"]["target_value"],
        ), ("不支持", "支持"))
        self.assertEqual((
            by_feature["脏污检测"]["source_value"],
            by_feature["脏污检测"]["target_value"],
        ), ("支持", "不支持"))

    def test_ai_rule_is_rejected_when_it_invents_a_fact(self):
        rules = validate_ai_difference_rules(
            {"rules": [{
                "feature_id": "max_suction",
                "feature_name": "最大吸力",
                "source_value": "22000Pa",
                "target_value": "50000Pa",
                "evidence_quote": "旧型号 22000Pa，新品 50000Pa",
            }]},
            source_text="旧型号最大吸力 22000Pa，新品 40000Pa",
            target_model="P30 Pro",
        )

        self.assertEqual(rules, [])

    def test_ai_rule_with_equal_values_is_ignored(self):
        rules = validate_ai_difference_rules(
            {"rules": [{
                "feature_id": "mop_pressure",
                "feature_name": "拖地压力",
                "source_value": "15N",
                "target_value": "15N",
                "evidence_quote": "新品 15N，旧型号 15N",
            }]},
            source_text="新品 15N，旧型号 15N",
            target_model="P30 Pro",
        )

        self.assertEqual(rules, [])

    def test_conflicting_sources_are_not_merged_by_confidence(self):
        first = parse_manual_difference_text("最大吸力 22000Pa 到 40000Pa", target_model="P30")
        second = parse_manual_difference_text("最大吸力 22000Pa 到 50000Pa", target_model="P30")

        merged = merge_difference_rules(first, second)

        self.assertEqual(len(merged), 2)
        self.assertTrue(all(rule["status"] == "source_conflict" for rule in merged))


if __name__ == "__main__":
    unittest.main()
