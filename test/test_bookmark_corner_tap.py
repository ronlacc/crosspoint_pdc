"""Run with python3 test/test_bookmark_corner_tap.py (requires a host C++20 compiler)."""

from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
reader_utils = (ROOT / "src/activities/reader/ReaderUtils.h").read_text()


def extract_block(source: str, signature: str) -> str:
    start = source.index(signature)
    opening = source.index("{", start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (source[end] == "{") - (source[end] == "}")
        end += 1
    return source[start:end]


prod_code = "\n\n".join([
    extract_block(reader_utils, "struct TouchPageTurn {").rstrip() + ";",
    "constexpr int BOOKMARK_CORNER_TAP_SIZE_PX = 100;",
    extract_block(reader_utils, "inline bool isBookmarkCornerTap("),
    extract_block(reader_utils, "inline TouchPageTurn detectTouchPageTurn("),
])

HARNESS = r"""
#include <cassert>
#include <cstdint>

struct GfxRenderer {
  int w = 480;
  int h = 800;
  int getScreenWidth() const { return w; }
  int getScreenHeight() const { return h; }
};

struct MappedInputManager {
  enum class SwipeDir : uint8_t { None, Left, Right };
  bool touch = true;
  bool tapped = false;
  int tapX = 0;
  int tapY = 0;
  SwipeDir swipe = SwipeDir::None;

  bool hasTouch() const { return touch; }
  SwipeDir wasSwipe() const { return swipe; }
  bool wasScreenTapped(int& x, int& y) const {
    if (!tapped) return false;
    x = tapX;
    y = tapY;
    return true;
  }
};

struct GpioStub {
  unsigned long lastTouchHeldMs() const { return 42; }
};
static GpioStub gpio;

struct CrossPointSettings {
  enum PAGE_TURN_GESTURE { TAP_AND_SWIPE = 0, TAP_ONLY = 1, SWIPE_ONLY = 2, INVERTED_TAP = 3, DISABLED = 4 };
  enum SHOW_READER_MENU { READER_MENU_OFF = 0, READER_MENU_TAP = 1, READER_MENU_SWIPE_UP = 2 };
  enum BOOKMARK_CORNER_TAP : uint8_t {
    BOOKMARK_CORNER_DISABLED = 0,
    BOOKMARK_CORNER_TOP_LEFT = 1,
    BOOKMARK_CORNER_TOP_RIGHT = 2,
    BOOKMARK_CORNER_BOTTOM_LEFT = 3,
    BOOKMARK_CORNER_BOTTOM_RIGHT = 4
  };
  uint8_t touchReaderControls = 1;
  uint8_t pageTurnGesture = TAP_AND_SWIPE;
  uint8_t previousPageGesture = TAP_AND_SWIPE;
  uint8_t showReaderMenu = READER_MENU_TAP;
  uint8_t bookmarkCornerTap = BOOKMARK_CORNER_DISABLED;
};
static CrossPointSettings SETTINGS;

inline bool gestureAllowsTap(uint8_t g) {
  return g == CrossPointSettings::TAP_AND_SWIPE || g == CrossPointSettings::TAP_ONLY ||
         g == CrossPointSettings::INVERTED_TAP;
}
inline bool gestureAllowsSwipe(uint8_t g) {
  return g == CrossPointSettings::TAP_AND_SWIPE || g == CrossPointSettings::SWIPE_ONLY;
}

""" + prod_code + r"""

int main() {
  GfxRenderer renderer{480, 800};
  MappedInputManager input;
  input.tapped = true;

  auto tap = [&](int x, int y) {
    input.tapX = x;
    input.tapY = y;
  };

  // 1. Disabled by default: never triggers at any corner.
  SETTINGS.bookmarkCornerTap = CrossPointSettings::BOOKMARK_CORNER_DISABLED;
  tap(0, 0);
  assert(!isBookmarkCornerTap(renderer, input));
  assert(detectTouchPageTurn(renderer, input).prev);
  tap(479, 0);
  assert(!isBookmarkCornerTap(renderer, input));
  assert(detectTouchPageTurn(renderer, input).next);

  // 2. Top left: [0..99] x [0..99]
  SETTINGS.bookmarkCornerTap = CrossPointSettings::BOOKMARK_CORNER_TOP_LEFT;
  tap(0, 0);
  assert(isBookmarkCornerTap(renderer, input));
  assert(!detectTouchPageTurn(renderer, input).prev && !detectTouchPageTurn(renderer, input).next);
  tap(99, 99);
  assert(isBookmarkCornerTap(renderer, input));
  tap(100, 99);
  assert(!isBookmarkCornerTap(renderer, input));
  assert(detectTouchPageTurn(renderer, input).prev);
  tap(99, 100);
  assert(!isBookmarkCornerTap(renderer, input));
  assert(detectTouchPageTurn(renderer, input).prev);

  // 3. Top right: [380..479] x [0..99]
  SETTINGS.bookmarkCornerTap = CrossPointSettings::BOOKMARK_CORNER_TOP_RIGHT;
  tap(380, 0);
  assert(isBookmarkCornerTap(renderer, input));
  assert(!detectTouchPageTurn(renderer, input).prev && !detectTouchPageTurn(renderer, input).next);
  tap(479, 99);
  assert(isBookmarkCornerTap(renderer, input));
  tap(379, 99);
  assert(!isBookmarkCornerTap(renderer, input));
  assert(detectTouchPageTurn(renderer, input).next);
  tap(479, 100);
  assert(!isBookmarkCornerTap(renderer, input));
  assert(detectTouchPageTurn(renderer, input).next);

  // 4. Bottom left: [0..99] x [700..799]
  SETTINGS.bookmarkCornerTap = CrossPointSettings::BOOKMARK_CORNER_BOTTOM_LEFT;
  tap(0, 700);
  assert(isBookmarkCornerTap(renderer, input));
  assert(!detectTouchPageTurn(renderer, input).prev && !detectTouchPageTurn(renderer, input).next);
  tap(99, 799);
  assert(isBookmarkCornerTap(renderer, input));
  tap(100, 799);
  assert(!isBookmarkCornerTap(renderer, input));
  assert(detectTouchPageTurn(renderer, input).prev);
  tap(99, 699);
  assert(!isBookmarkCornerTap(renderer, input));
  assert(detectTouchPageTurn(renderer, input).prev);

  // 5. Bottom right: [380..479] x [700..799]
  SETTINGS.bookmarkCornerTap = CrossPointSettings::BOOKMARK_CORNER_BOTTOM_RIGHT;
  tap(380, 700);
  assert(isBookmarkCornerTap(renderer, input));
  assert(!detectTouchPageTurn(renderer, input).prev && !detectTouchPageTurn(renderer, input).next);
  tap(479, 799);
  assert(isBookmarkCornerTap(renderer, input));
  tap(379, 799);
  assert(!isBookmarkCornerTap(renderer, input));
  assert(detectTouchPageTurn(renderer, input).next);
  tap(479, 699);
  assert(!isBookmarkCornerTap(renderer, input));
  assert(detectTouchPageTurn(renderer, input).next);

  // 6. reserveReaderMenuTap == false (definition viewer): does not suppress page turns.
  tap(479, 799);
  assert(detectTouchPageTurn(renderer, input, false, false).next);

  // 7. touchReaderControls == 0: disables corner tap.
  SETTINGS.touchReaderControls = 0;
  assert(!isBookmarkCornerTap(renderer, input));

  return 0;
}
"""


class TestBookmarkCornerTap(unittest.TestCase):
    def test_static_wiring(self):
        settings_h = (ROOT / "src/CrossPointSettings.h").read_text()
        self.assertIn("enum BOOKMARK_CORNER_TAP", settings_h)
        self.assertIn("uint8_t bookmarkCornerTap = BOOKMARK_CORNER_DISABLED;", settings_h)

        settings_list = (ROOT / "src/SettingsList.cpp").read_text()
        self.assertIn("StrId::STR_BOOKMARK_CORNER_TAP, &CrossPointSettings::bookmarkCornerTap", settings_list)

        settings_act = (ROOT / "src/activities/settings/SettingsActivity.cpp").read_text()
        self.assertIn("field == &CrossPointSettings::bookmarkCornerTap", settings_act)

        settings_html = (ROOT / "src/network/html/SettingsPage.html").read_text()
        self.assertIn("'bookmarkCornerTap'", settings_html)

        epub_cpp = (ROOT / "src/activities/reader/EpubReaderActivity.cpp").read_text()
        self.assertIn("ReaderUtils::isBookmarkCornerTap(renderer, mappedInput)", epub_cpp)

    def test_corner_tap_geometry(self):
        with tempfile.NamedTemporaryFile("w", suffix=".cpp", delete=False) as f:
            f.write(HARNESS)
            src_path = Path(f.name)
        bin_path = src_path.with_suffix(".bin")
        try:
            subprocess.run(["g++", "-std=c++20", "-Wall", "-Wextra", "-Werror", str(src_path), "-o", str(bin_path)],
                           check=True, capture_output=True, text=True)
            res = subprocess.run([str(bin_path)], check=True, capture_output=True, text=True)
            self.assertEqual(res.returncode, 0)
        finally:
            if src_path.exists():
                src_path.unlink()
            if bin_path.exists():
                bin_path.unlink()


if __name__ == "__main__":
    unittest.main()
