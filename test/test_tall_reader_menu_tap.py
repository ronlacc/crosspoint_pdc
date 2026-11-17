"""Run with python3 test/test_tall_reader_menu_tap.py (requires a host C++20 compiler)."""

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
    extract_block(reader_utils, "inline bool isInTouchMenuTapZone("),
    extract_block(reader_utils, "inline TouchPageTurn detectTouchPageTurn("),
    extract_block(reader_utils, "inline bool isTouchMenuTap("),
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
  uint8_t touchReaderControls = 1;
  uint8_t pageTurnGesture = TAP_AND_SWIPE;
  uint8_t previousPageGesture = TAP_AND_SWIPE;
  uint8_t showReaderMenu = READER_MENU_TAP;
};
static CrossPointSettings SETTINGS;

inline bool gestureAllowsTap(uint8_t g) {
  return g == CrossPointSettings::TAP_AND_SWIPE || g == CrossPointSettings::TAP_ONLY ||
         g == CrossPointSettings::INVERTED_TAP;
}
inline bool gestureAllowsSwipe(uint8_t g) {
  return g == CrossPointSettings::TAP_AND_SWIPE || g == CrossPointSettings::SWIPE_ONLY;
}
inline bool isBookmarkCornerTap(const GfxRenderer&, const MappedInputManager&) { return false; }

""" + prod_code + r"""

int main() {
  GfxRenderer renderer{480, 800};  // thirds: [0..159], [160..319], [320..479]
  MappedInputManager input;
  input.tapped = true;

  const int colX[3] = {80, 240, 400};
  const int rowY[3] = {100, 400, 700};

  // 1. Default mode: middle column (top, center, bottom) opens menu and does not turn pages.
  for (int r = 0; r < 3; ++r) {
    input.tapY = rowY[r];

    input.tapX = colX[0];
    assert(!isTouchMenuTap(renderer, input));
    auto leftTurn = detectTouchPageTurn(renderer, input);
    assert(leftTurn.prev && !leftTurn.next);

    input.tapX = colX[1];
    assert(isTouchMenuTap(renderer, input));
    auto midTurn = detectTouchPageTurn(renderer, input);
    assert(!midTurn.prev && !midTurn.next);

    input.tapX = colX[2];
    assert(!isTouchMenuTap(renderer, input));
    auto rightTurn = detectTouchPageTurn(renderer, input);
    assert(!rightTurn.prev && rightTurn.next);
  }

  // 2. Exact boundary pixels at top and bottom edges.
  input.tapY = 0;
  input.tapX = 159;
  assert(!isTouchMenuTap(renderer, input));
  assert(detectTouchPageTurn(renderer, input).prev);

  input.tapX = 160;
  assert(isTouchMenuTap(renderer, input));
  assert(!detectTouchPageTurn(renderer, input).prev && !detectTouchPageTurn(renderer, input).next);

  input.tapY = 799;
  input.tapX = 319;
  assert(isTouchMenuTap(renderer, input));
  assert(!detectTouchPageTurn(renderer, input).prev && !detectTouchPageTurn(renderer, input).next);

  input.tapX = 320;
  assert(!isTouchMenuTap(renderer, input));
  assert(detectTouchPageTurn(renderer, input).next);

  // 3. Inverted tap: middle column still reserved for menu; left/right flip.
  SETTINGS.pageTurnGesture = CrossPointSettings::INVERTED_TAP;
  input.tapY = 100;
  input.tapX = 240;
  assert(isTouchMenuTap(renderer, input));
  assert(!detectTouchPageTurn(renderer, input).prev && !detectTouchPageTurn(renderer, input).next);

  input.tapX = 80;
  assert(detectTouchPageTurn(renderer, input).next);
  input.tapX = 400;
  assert(detectTouchPageTurn(renderer, input).prev);
  SETTINGS.pageTurnGesture = CrossPointSettings::TAP_AND_SWIPE;

  // 4. reserveReaderMenuTap == false (e.g. definition viewer): middle column turns page.
  input.tapY = 100;
  input.tapX = 240;
  assert(detectTouchPageTurn(renderer, input, false, false).next);

  // 5. showReaderMenu == READER_MENU_OFF: middle column does not open menu and turns page.
  SETTINGS.showReaderMenu = CrossPointSettings::READER_MENU_OFF;
  assert(!isTouchMenuTap(renderer, input));
  assert(detectTouchPageTurn(renderer, input).next);

  return 0;
}
"""


class TestTallReaderMenuTap(unittest.TestCase):
    def test_tall_menu_tap_zones(self):
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
