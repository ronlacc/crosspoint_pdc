# CrossPoint Reader (Personal Fork)

> This repository is a personal fork of [CrossPoint Reader](https://github.com/crosspoint-reader/crosspoint-reader), customized primarily for the **Boox Picco** (`pio run -e picco`).
>
> For official releases, device support, and upstream community development, please visit the [main CrossPoint Reader repository](https://github.com/crosspoint-reader/crosspoint-reader) or [crosspointreader.com](https://crosspointreader.com).

### Custom Features on `personalBranch`

- **Secondary Dictionary** (`feat/secondary-dictionary`): Configure a secondary StarDict dictionary in Reader Settings to query concurrently and display combined definitions (including recursive lookups).
- **Immediate Lookup** (`feat/immediate-lookup`): Optional Reader Settings toggle so tapping and holding a word immediately opens its dictionary definition instead of the action menu.
- **Tall Reader Menu Tap** (`Tall_ReaderMenuTap`): Extends the Reader Menu tap target across the entire middle vertical third (top-middle, center, and bottom-middle nonants).
- **Tap Corner to Bookmark** (`bookmark-corner-tap`): Adds a **Tap Corner to Bookmark** setting under **Settings → Controls → Taps and gestures** (`Disabled`, `Top left`, `Top right`, `Bottom left`, `Bottom right`) to toggle bookmarks via a 100×100 px corner tap while reading.

