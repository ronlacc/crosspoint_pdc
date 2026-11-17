"""Run with python3 test/test_immediate_lookup.py (requires a host C++20 compiler)."""

from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class TestImmediateLookupStatic(unittest.TestCase):
    def test_settings_member_exists(self):
        settings_header = (ROOT / "src/CrossPointSettings.h").read_text()
        self.assertIn("uint8_t immediateLookupEnabled = 0;", settings_header)

    def test_translation_entry_exists(self):
        yaml_content = (ROOT / "lib/I18n/translations/english.yaml").read_text()
        self.assertIn('STR_IMMEDIATE_LOOKUP: "Immediate Lookup"', yaml_content)

    def test_settings_list_emission(self):
        settings_list_cpp = (ROOT / "src/SettingsList.cpp").read_text()
        self.assertIn("emit(SettingInfo::Toggle(StrId::STR_IMMEDIATE_LOOKUP, &CrossPointSettings::immediateLookupEnabled,", settings_list_cpp)

    def test_clip_selection_behavior(self):
        clip_cpp = (ROOT / "src/activities/reader/ClipSelectionActivity.cpp").read_text()
        self.assertIn("if (SETTINGS.immediateLookupEnabled && lookupAvailable && mode == Mode::Clip)", clip_cpp)
        self.assertIn("confirmSelection(ClippingResult::Action::Lookup);", clip_cpp)


class TestImmediateLookupCompilation(unittest.TestCase):
    def test_order_and_logic(self):
        test_cpp = r"""
#include <cassert>
#include <cstdint>
#include <string>
#include <vector>

enum class StrId : uint16_t {
  STR_NONE,
  STR_DICTIONARY,
  STR_SECONDARY_DICTIONARY,
  STR_IMMEDIATE_LOOKUP,
  STR_SAVE_VOCABULARY_LOOKUPS,
  STR_CAT_READER,
  STR_CAT_CONTROLS,
};

struct BoardConfig {
  static inline bool touchAvailable = true;
  static bool hasTouch() { return touchAvailable; }
};

struct CrossPointSettings {
  uint8_t immediateLookupEnabled = 0;
  uint8_t vocabularyHistoryEnabled = 0;
};
static CrossPointSettings SETTINGS;

struct SettingInfo {
  StrId nameId = StrId::STR_NONE;
  uint8_t* valuePtr = nullptr;
  StrId category = StrId::STR_CAT_READER;
  const char* key = nullptr;
};

inline bool isHiddenOnDevice(const SettingInfo& s) {
  switch (s.nameId) {
    case StrId::STR_IMMEDIATE_LOOKUP:
      return !BoardConfig::hasTouch();
    default:
      return false;
  }
}

template <typename Fn>
void forEachBaseSettingMock(Fn&& emit) {
  SettingInfo imm;
  imm.nameId = StrId::STR_IMMEDIATE_LOOKUP;
  imm.valuePtr = &SETTINGS.immediateLookupEnabled;
  imm.category = StrId::STR_CAT_READER;
  imm.key = "immediateLookupEnabled";
  emit(imm);

  SettingInfo vocab;
  vocab.nameId = StrId::STR_SAVE_VOCABULARY_LOOKUPS;
  vocab.valuePtr = &SETTINGS.vocabularyHistoryEnabled;
  vocab.category = StrId::STR_CAT_READER;
  vocab.key = "vocabularyHistoryEnabled";
  emit(vocab);
}

struct DictionaryEntry {
  std::string name;
};

template <typename Wants, typename Visit>
void forEachSettingMock(const std::vector<DictionaryEntry>* dictionaries, Wants wants, Visit visit) {
  bool dictionaryPending = dictionaries && !dictionaries->empty();
  const auto visitDictionary = [&] {
    dictionaryPending = false;
    if (wants("dictionaryName")) {
      SettingInfo s;
      s.nameId = StrId::STR_DICTIONARY;
      s.key = "dictionaryName";
      visit(s);
    }
    if (wants("secondaryDictionaryName")) {
      SettingInfo s;
      s.nameId = StrId::STR_SECONDARY_DICTIONARY;
      s.key = "secondaryDictionaryName";
      visit(s);
    }
  };
  auto each = [&](SettingInfo& s) {
    if (isHiddenOnDevice(s)) return;
    if (s.valuePtr == &SETTINGS.immediateLookupEnabled) {
      if (!dictionaryPending) return;
      visitDictionary();
    }
    if (s.valuePtr == &SETTINGS.vocabularyHistoryEnabled) {
      if (dictionaryPending) {
        visitDictionary();
      } else if (!dictionaries || dictionaries->empty()) {
        return;
      }
    }
    if (dictionaryPending && s.category == StrId::STR_CAT_CONTROLS) visitDictionary();
    if (!wants(s.key)) return;
    visit(s);
  };
  forEachBaseSettingMock(each);
  if (dictionaryPending) visitDictionary();
}

enum class Mode : uint8_t { Clip, Lookup, DefinitionLookup };
enum class Action : uint8_t { Lookup, Clip, Bookmark };

struct MockClipSelectionActivity {
  Mode mode = Mode::Clip;
  bool lookupAvailable = true;
  int initialX = 100;
  int initialY = 200;
  bool confirmedLookup = false;
  bool requestedUpdate = false;

  int wordAt(int x, int y) const { return (x >= 0 && y >= 0) ? 1 : -1; }

  void confirmSelection(Action action) {
    if (action == Action::Lookup) {
      confirmedLookup = true;
    }
  }

  void onEnter() {
    if (initialX >= 0) {
      const int hit = wordAt(initialX, initialY);
      if (hit < 0) return;
      if (SETTINGS.immediateLookupEnabled && lookupAvailable && mode == Mode::Clip) {
        confirmSelection(Action::Lookup);
        return;
      }
    }
    requestedUpdate = true;
  }
};

int main() {
  // Test 1: With dictionaries, touch board -> verify order: Dictionary, Secondary Dictionary, Immediate Lookup, Save Vocabulary Lookups
  BoardConfig::touchAvailable = true;
  std::vector<DictionaryEntry> dicts = {{"Dict1"}};
  std::vector<StrId> order;
  forEachSettingMock(&dicts, [](const char*) { return true; }, [&](const SettingInfo& s) {
    order.push_back(s.nameId);
  });
  assert(order.size() == 4);
  assert(order[0] == StrId::STR_DICTIONARY);
  assert(order[1] == StrId::STR_SECONDARY_DICTIONARY);
  assert(order[2] == StrId::STR_IMMEDIATE_LOOKUP);
  assert(order[3] == StrId::STR_SAVE_VOCABULARY_LOOKUPS);

  // Test 2: Without dictionaries -> neither Immediate Lookup nor Save Vocabulary Lookups appear
  std::vector<StrId> orderNoDict;
  forEachSettingMock(nullptr, [](const char*) { return true; }, [&](const SettingInfo& s) {
    orderNoDict.push_back(s.nameId);
  });
  assert(orderNoDict.empty());

  // Test 3: Non-touch board with dictionaries -> Immediate Lookup is hidden, Dictionary and Save Vocabulary still appear
  BoardConfig::touchAvailable = false;
  std::vector<StrId> orderNonTouch;
  forEachSettingMock(&dicts, [](const char*) { return true; }, [&](const SettingInfo& s) {
    orderNonTouch.push_back(s.nameId);
  });
  assert(orderNonTouch.size() == 3);
  assert(orderNonTouch[0] == StrId::STR_DICTIONARY);
  assert(orderNonTouch[1] == StrId::STR_SECONDARY_DICTIONARY);
  assert(orderNonTouch[2] == StrId::STR_SAVE_VOCABULARY_LOOKUPS);

  // Test 4: ClipSelectionActivity with immediateLookupEnabled = 1
  SETTINGS.immediateLookupEnabled = 1;
  MockClipSelectionActivity act1;
  act1.onEnter();
  assert(act1.confirmedLookup == true);
  assert(act1.requestedUpdate == false);

  // Test 5: ClipSelectionActivity with immediateLookupEnabled = 0 (default behavior)
  SETTINGS.immediateLookupEnabled = 0;
  MockClipSelectionActivity act2;
  act2.onEnter();
  assert(act2.confirmedLookup == false);
  assert(act2.requestedUpdate == true);

  // Test 6: ClipSelectionActivity with immediateLookupEnabled = 1, but lookup not available
  SETTINGS.immediateLookupEnabled = 1;
  MockClipSelectionActivity act3;
  act3.lookupAvailable = false;
  act3.onEnter();
  assert(act3.confirmedLookup == false);
  assert(act3.requestedUpdate == true);

  // Test 7: ClipSelectionActivity with immediateLookupEnabled = 1, but mode is DefinitionLookup
  SETTINGS.immediateLookupEnabled = 1;
  MockClipSelectionActivity act4;
  act4.mode = Mode::DefinitionLookup;
  act4.onEnter();
  assert(act4.confirmedLookup == false);
  assert(act4.requestedUpdate == true);

  return 0;
}
"""
        with tempfile.NamedTemporaryFile("w", suffix=".cpp", delete=False) as f:
            f.write(test_cpp)
            src_path = Path(f.name)

        bin_path = src_path.with_suffix(".bin")
        try:
            compile_cmd = ["g++", "-std=c++20", "-O2", str(src_path), "-o", str(bin_path)]
            subprocess.run(compile_cmd, check=True, capture_output=True)
            res = subprocess.run([str(bin_path)], check=True, capture_output=True, text=True)
            self.assertEqual(res.returncode, 0)
        finally:
            if src_path.exists():
                src_path.unlink()
            if bin_path.exists():
                bin_path.unlink()


if __name__ == "__main__":
    unittest.main()
