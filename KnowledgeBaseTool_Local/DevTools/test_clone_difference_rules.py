import unittest

from clone_difference_rules import (
    merge_difference_rules,
    parse_manual_difference_text,
    parse_manual_difference_text_with_warnings,
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

    def test_compound_obstacle_heights_are_not_cross_paired_within_one_model(self):
        rules, warnings = parse_manual_difference_text_with_warnings(
            """越障高度：P20 MAX 双层门槛最高 8.8cm，日常越障 4.5cm（双层为 4.5+4.3cm）；P30 Member 双层门槛最高 8cm，日常越障 4cm（双层为 4+4cm）。
拖地水温：P20 MAX 为 60°C；P30 Member 为 58°C。""",
            target_model="P30 Member",
            source_model="P20 MAX",
        )

        obstacle_rules = [rule for rule in rules if rule["feature_id"] == "obstacle_crossing_height"]
        self.assertEqual(len(obstacle_rules), 1)
        self.assertIn("最高 8.8cm", obstacle_rules[0]["source_value"])
        self.assertIn("日常越障 4cm", obstacle_rules[0]["target_value"])
        self.assertFalse(any(
            rule["source_value"] == "8.8cm" and rule["target_value"] == "4.5cm"
            for rule in rules
        ))
        self.assertEqual(warnings, [])

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

    def test_semicolon_model_clauses_keep_compound_dimensions_and_units(self):
        rules = parse_manual_difference_text(
            """主机尺寸：智净2.0 264*241*110mm；智净 265mm*232mm*1100mm
底座尺寸：智净2.0 352*316*110mm；智净 330mm*316mm*112mm
产品净重：智净2.0 5.8kg；智净 4.2kg
风机转速：智净2.0 150000rpm；智净 120000rpm
静音烘干噪音：智净2.0 48dB；智净 55dB""",
            target_model="智净2.0",
        )

        self.assertEqual(
            [(rule["source_value"], rule["target_value"]) for rule in rules],
            [
                ("265mm*232mm*1100mm", "264*241*110mm"),
                ("330mm*316mm*112mm", "352*316*110mm"),
                ("4.2kg", "5.8kg"),
                ("120000rpm", "150000rpm"),
                ("55dB", "48dB"),
            ],
        )
        self.assertEqual(
            [rule["feature_name"] for rule in rules],
            ["主机尺寸", "底座尺寸", "产品净重", "风机转速", "静音烘干噪音"],
        )
        self.assertTrue(all(rule["feature_id"].startswith("manual_feature_") for rule in rules))

    def test_semicolon_model_clauses_support_full_catalog_value_types(self):
        rules = parse_manual_difference_text(
            """配色：智净2.0 极光白；智净 余墨灰
额定功率：智净2.0 500W；智净 400W
链接APP（智能互联）：智净2.0 支持；智净 不支持""",
            target_model="智净2.0",
            source_model="智净",
        )

        self.assertEqual(
            [(rule["feature_name"], rule["source_value"], rule["target_value"]) for rule in rules],
            [
                ("配色", "余墨灰", "极光白"),
                ("额定功率", "400W", "500W"),
                ("链接APP（智能互联）", "不支持", "支持"),
            ],
        )

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
        second[0]["evidence_sources"] = ["parameter_check"]

        merged = merge_difference_rules(first, second)

        self.assertEqual(len(merged), 2)
        self.assertTrue(all(rule["status"] == "source_conflict" for rule in merged))

    def test_same_source_multiple_assertions_are_ambiguous_not_source_conflict(self):
        first = parse_manual_difference_text("最大吸力 22000Pa 到 40000Pa", target_model="P30")
        second = parse_manual_difference_text("最大吸力 22000Pa 到 50000Pa", target_model="P30")

        merged = merge_difference_rules(first, second)

        self.assertEqual(len(merged), 2)
        self.assertTrue(all(rule["status"] == "needs_confirmation" for rule in merged))
        self.assertTrue(all(rule["difference_type"] == "value_changed" for rule in merged))

    def test_explicit_context_keeps_same_feature_rules_separate(self):
        rules = parse_manual_difference_text(
            "自动模式续航时间：P30 40min；P20 30min\n强力模式续航时间：P30 20min；P20 15min",
            target_model="P30",
            source_model="P20",
        )

        self.assertEqual([rule["context"] for rule in rules], ["自动模式", "强力模式"])
        self.assertEqual(len(merge_difference_rules(rules)), 2)

    def test_ambiguous_model_summary_is_reported_as_warning(self):
        rules, warnings = parse_manual_difference_text_with_warnings(
            "P20 有 4 种模式、4000mAh；P30 有 2 种模式、2500mAh",
            target_model="P30",
            source_model="P20",
        )

        self.assertEqual(rules, [])
        self.assertEqual(len(warnings), 2)
        self.assertTrue(all(item["code"] == "ambiguous_model_summary" for item in warnings))

    def test_model_summary_does_not_cross_pair_unrelated_values(self):
        rules = parse_manual_difference_text(
            """A30 2.0 是主力款，有 4 种清洁模式、4000mAh 软包大电池；
A30 Ultra 配置精简，2 种清洁模式、电池容量 2500mAh
5. 电池类型：A30 Ultra 非软包电池；A30 2.0 软包电池
6. 电池容量：A30 Ultra 2500mAh；A30 2.0 4000mAh
9. 清水箱容量：A30 Ultra 870ml；A30 2.0 900ml""",
            target_model="A30 Ultra",
            source_model="A30 2.0",
        )

        self.assertEqual(
            [(rule["feature_name"], rule["source_value"], rule["target_value"]) for rule in rules],
            [
                ("电池类型", "软包电池", "非软包电池"),
                ("电池容量", "4000mAh", "2500mAh"),
                ("水箱容量", "900ml", "870ml"),
            ],
        )
        self.assertFalse(any(rule["status"] == "source_conflict" for rule in merge_difference_rules(rules)))


if __name__ == "__main__":
    unittest.main()
