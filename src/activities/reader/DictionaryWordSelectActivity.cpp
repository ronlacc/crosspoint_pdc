#include "DictionaryWordSelectActivity.h"

#include <FontCacheManager.h>
#include <GfxRenderer.h>
#include <Memory.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>

#include "CrossPointSettings.h"
#include "DictionaryDefinitionActivity.h"
#include "components/UITheme.h"

namespace {

constexpr unsigned long POPUP_DURATION_MS = 1500;

void indexBuildYield(void*) { vTaskDelay(1); }

void escapeHtmlText(std::string& out, const char* in) {
  if (!in) return;
  for (const char* p = in; *p; ++p) {
    switch (*p) {
      case '&': out += "&amp;"; break;
      case '<': out += "&lt;"; break;
      case '>': out += "&gt;"; break;
      case '"': out += "&quot;"; break;
      default: out.push_back(*p); break;
    }
  }
}

void escapePlainTextToHtml(std::string& out, const std::string& in) {
  for (char c : in) {
    switch (c) {
      case '\n': out += "<br/>"; break;
      case '&': out += "&amp;"; break;
      case '<': out += "&lt;"; break;
      case '>': out += "&gt;"; break;
      case '"': out += "&quot;"; break;
      default: out.push_back(c); break;
    }
  }
}

void combineDefinitions(const std::string& primDef, const std::string& primHead, bool primHtml,
                        const char* primName, const std::string& secDef, const std::string& secHead,
                        bool secHtml, const char* secName, std::string& defOut, std::string& headOut,
                        bool& htmlOut) {
  headOut = !primHead.empty() ? primHead : secHead;
  htmlOut = primHtml || secHtml;
  defOut.clear();
  defOut.reserve(primDef.size() + secDef.size() + 256);

  if (htmlOut) {
    if (primName && primName[0]) {
      defOut += "<h2>[";
      escapeHtmlText(defOut, primName);
      defOut += "]</h2>\n";
    }
    if (primHtml) {
      defOut += primDef;
    } else {
      defOut += "<p>";
      escapePlainTextToHtml(defOut, primDef);
      defOut += "</p>";
    }

    defOut += "\n<hr/>\n";
    if (secName && secName[0]) {
      defOut += "<h2>[";
      escapeHtmlText(defOut, secName);
      defOut += "]</h2>\n";
    }
    if (secHtml) {
      defOut += secDef;
    } else {
      defOut += "<p>";
      escapePlainTextToHtml(defOut, secDef);
      defOut += "</p>";
    }
  } else {
    if (primName && primName[0]) {
      defOut.push_back('\x01');
      defOut += "[";
      defOut += primName;
      defOut += "]\n";
    }
    defOut += primDef;

    defOut += "\n\n";

    if (secName && secName[0]) {
      defOut.push_back('\x01');
      defOut += "[";
      defOut += secName;
      defOut += "]\n";
    }
    defOut += secDef;
  }
}

void formatSingleDefinition(const std::string& def, const std::string& head, bool isHtml,
                            const char* name, std::string& defOut, std::string& headOut,
                            bool& htmlOut) {
  headOut = head;
  htmlOut = isHtml;
  defOut.clear();
  if (name && name[0] != '\0') {
    if (isHtml) {
      defOut.reserve(def.size() + 128);
      defOut += "<h2>[";
      escapeHtmlText(defOut, name);
      defOut += "]</h2>\n";
      defOut += def;
    } else {
      defOut.reserve(def.size() + 64);
      defOut.push_back('\x01');
      defOut += "[";
      defOut += name;
      defOut += "]\n";
      defOut += def;
    }
  } else {
    defOut = def;
  }
}

}  // namespace

void DictionaryWordSelectActivity::onEnter() {
  Activity::onEnter();
  fontId = SETTINGS.getReaderFontId();
  lookupPending = true;
  popupMsg = StrId::STR_DICT_LOOKING_UP;
  popup = Popup::Busy;
  requestUpdate();
}

void DictionaryWordSelectActivity::performLookup() {
  {
    RenderLock lock;
    popupMsg = StrId::STR_DICT_LOOKING_UP;
    popup = Popup::Busy;
  }
  const bool primConfigured = SETTINGS.dictionaryName[0] != '\0';
  if (!dictOpenAttempted) {
    dictOpenAttempted = true;
    dictOpenOk = primConfigured && dict.open(SETTINGS.dictionaryName);
    // needsIndex() opens and validates the .qidx sidecar, so ask it once per
    // open rather than once per word: the answer only changes when we build
    // the sidecar ourselves, which is handled below.
    dictNeedsIndex = dictOpenOk && dict.needsIndex();
  }

  const bool hasSecondary = SETTINGS.secondaryDictionaryName[0] != '\0' &&
                            strcmp(SETTINGS.dictionaryName, SETTINGS.secondaryDictionaryName) != 0;
  if (hasSecondary && !secondaryDictOpenAttempted) {
    secondaryDictOpenAttempted = true;
    secondaryDictOpenOk = secondaryDict.open(SETTINGS.secondaryDictionaryName);
    secondaryDictNeedsIndex = secondaryDictOpenOk && secondaryDict.needsIndex();
  }

  {
    RenderLock lock;
    const bool needsIndexing = dictNeedsIndex || (hasSecondary && secondaryDictNeedsIndex);
    popupMsg = needsIndexing ? StrId::STR_DICT_INDEXING : StrId::STR_DICT_LOOKING_UP;
  }
  requestUpdateAndWait();  // paint the page + busy popup before blocking on SD

  bool ok = dictOpenOk;
  Dictionary::IndexResult indexResult = Dictionary::IndexResult::Ok;
  if (ok && dictNeedsIndex) {
    ok = dict.buildIndex(&indexBuildYield, nullptr, &indexResult);
    dictNeedsIndex = !ok;  // a successful build leaves the sidecar fresh; a failed one retries
  }

  bool secOk = hasSecondary && secondaryDictOpenOk;
  Dictionary::IndexResult secIndexResult = Dictionary::IndexResult::Ok;
  if (secOk && secondaryDictNeedsIndex) {
    secOk = secondaryDict.buildIndex(&indexBuildYield, nullptr, &secIndexResult);
    secondaryDictNeedsIndex = !secOk;
  }

  std::string primDef, primHead;
  Dictionary::LookupResult primResult = Dictionary::LookupResult::NotFound;
  const bool primFound = ok && dict.lookup(lookupText.c_str(), primDef, primHead, &primResult);

  std::string secDef, secHead;
  Dictionary::LookupResult secResult = Dictionary::LookupResult::NotFound;
  const bool secFound = secOk && secondaryDict.lookup(lookupText.c_str(), secDef, secHead, &secResult);

  std::string finalDefinition;
  std::string finalHeadword;
  bool finalHtml = false;
  bool found = false;

  if (primFound && secFound) {
    found = true;
    combineDefinitions(primDef, primHead, dict.definitionsAreHtml(), SETTINGS.dictionaryName,
                       secDef, secHead, secondaryDict.definitionsAreHtml(), SETTINGS.secondaryDictionaryName,
                       finalDefinition, finalHeadword, finalHtml);
  } else if (primFound) {
    found = true;
    formatSingleDefinition(primDef, primHead, dict.definitionsAreHtml(),
                           hasSecondary ? SETTINGS.dictionaryName : "",
                           finalDefinition, finalHeadword, finalHtml);
  } else if (secFound) {
    found = true;
    formatSingleDefinition(secDef, secHead, secondaryDict.definitionsAreHtml(),
                           SETTINGS.secondaryDictionaryName,
                           finalDefinition, finalHeadword, finalHtml);
  }

  if (found) {
    {
      RenderLock lock;
      popup = Popup::None;
      page.reset();
    }
    if (SETTINGS.vocabularyHistoryEnabled &&
        !VocabularyStore::append(vocabulary, lookupText, finalHeadword, finalDefinition, finalHtml)) {
      LOG_ERR("VOCAB", "Could not save successful dictionary lookup");
    }
    auto activity = makeUniqueNoThrow<DictionaryDefinitionActivity>(renderer, mappedInput, std::move(finalHeadword),
                                                                    std::move(finalDefinition), finalHtml);
    if (!activity || !activity->enableLookup(dict, std::move(lookupText),
                                            hasSecondary ? &secondaryDict : nullptr,
                                            SETTINGS.dictionaryName,
                                            hasSecondary ? SETTINGS.secondaryDictionaryName : "",
                                            dict.definitionsAreHtml(),
                                            hasSecondary ? secondaryDict.definitionsAreHtml() : false)) {
      LOG_ERR("DICT", "OOM: definition activity");
      popup = Popup::Error;
      popupMsg = StrId::STR_DICT_LOW_MEMORY;
      popupTime = millis();
      requestUpdate();
      return;
    }
    startActivityForResult(std::move(activity), [this](const ActivityResult& result) {
      setResult(ActivityResult{result});
      finish();
    });
    return;
  }

  // Name the failure: a genuine miss is "Not found"; a word that WAS found but
  // couldn't be read is a real error — and we distinguish decompression from a
  // low-memory allocation from a generic read error.
  const bool hadError = (primConfigured && !ok && indexResult != Dictionary::IndexResult::Ok) ||
                        (hasSecondary && !secOk && secIndexResult != Dictionary::IndexResult::Ok);
  if (hadError) {
    popup = Popup::Error;
    const Dictionary::IndexResult errIdx =
        (primConfigured && !ok && indexResult != Dictionary::IndexResult::Ok) ? indexResult : secIndexResult;
    switch (errIdx) {
      case Dictionary::IndexResult::LowMemory:
        popupMsg = StrId::STR_DICT_LOW_MEMORY;
        break;
      case Dictionary::IndexResult::ReadError:
        popupMsg = StrId::STR_DICT_READ_FAILED;
        break;
      case Dictionary::IndexResult::Ok:
      default:
        popupMsg = StrId::STR_DICT_ERROR;
        break;
    }
  } else if ((primConfigured && !ok) || (hasSecondary && !secOk && !primFound)) {
    popup = Popup::Error;
    popupMsg = StrId::STR_DICT_ERROR;
  } else {
    Dictionary::LookupResult errResult = (primResult != Dictionary::LookupResult::NotFound) ? primResult : secResult;
    switch (errResult) {
      case Dictionary::LookupResult::Decompress:
        popup = Popup::Error;
        popupMsg = StrId::STR_DICT_DECOMPRESS_ERROR;
        break;
      case Dictionary::LookupResult::LowMemory:
        popup = Popup::Error;
        popupMsg = StrId::STR_DICT_LOW_MEMORY;
        break;
      case Dictionary::LookupResult::ReadError:
        popup = Popup::Error;
        popupMsg = StrId::STR_DICT_READ_FAILED;
        break;
      case Dictionary::LookupResult::NotFound:
      case Dictionary::LookupResult::Found:
      default:
        popup = Popup::NotFound;
        popupMsg = StrId::STR_DICT_NOT_FOUND;
        break;
    }
  }
  popupTime = millis();
  requestUpdate();
}

void DictionaryWordSelectActivity::loop() {
  if (lookupPending) {
    lookupPending = false;
    performLookup();
    return;
  }
  if (popup == Popup::NotFound || popup == Popup::Error) {
    if (millis() - popupTime >= POPUP_DURATION_MS) {
      result.isCancelled = popup == Popup::Error;
      finish();
    }
  }
}

void DictionaryWordSelectActivity::render(RenderLock&&) {
  renderer.clearScreen();

  auto* fcm = renderer.getFontCacheManager();
  auto scope = fcm->createPrewarmScope();
  if (page) page->render(renderer, fontId, marginLeft, marginTop);
  scope.endScanAndPrewarm();
  if (page) page->render(renderer, fontId, marginLeft, marginTop);

  if (popup != Popup::None) {
    GUI.drawPopup(renderer, I18N.get(popupMsg));
    return;
  }
  renderer.displayBuffer(HalDisplay::FAST_REFRESH);
}
