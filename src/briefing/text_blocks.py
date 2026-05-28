# src/briefing/text_blocks.py
"""
Rule-based text blocks keyed by mode and CDI level.
All slots are filled strictly from RegionReport values — no invented facts.

Slots available:
  {region}, {cdi}, {cdi_label}, {spi_3m:.2f}, {spi_3m_delta:+.2f},
  {soil_moisture_pct:.0f}, {vhi:.1f}, {vhi_delta:+.1f},
  {pct_critical_pct:.0f}, {spi_3m_percentile}, {data_timestamp},
  {coverage_pct:.0%}, {overall}, {trend_de}, {trend_de_bulletin}
"""
from __future__ import annotations

# Keys: mode -> cdi_level -> template string
LAGE_BLOCKS: dict[str, dict[int, str]] = {
    "behoerden": {
        0: "{region}: CDI {cdi} ({cdi_label}). SPI-3m {spi_3m:.2f}. Bodenfeuchte {soil_moisture_pct:.0f}% nFK. VHI {vhi:.1f}.",
        1: "{region}: CDI {cdi} ({cdi_label}). SPI-3m {spi_3m:.2f}. Bodenfeuchte {soil_moisture_pct:.0f}% nFK. VHI {vhi:.1f}.",
        2: "{region}: CDI {cdi} ({cdi_label}). SPI-3m {spi_3m:.2f} (unter Schwelle -0.84). Bodenfeuchte {soil_moisture_pct:.0f}% nFK. VHI {vhi:.1f}.",
        3: "{region}: CDI {cdi} ({cdi_label}). SPI-3m {spi_3m:.2f}. Bodenfeuchte {soil_moisture_pct:.0f}% nFK. VHI {vhi:.1f}. Erhöhte Aufmerksamkeit erforderlich.",
        4: "{region}: CDI {cdi} ({cdi_label}). SPI-3m {spi_3m:.2f}. Bodenfeuchte {soil_moisture_pct:.0f}% nFK. VHI {vhi:.1f}. Sofortmaßnahmen prüfen.",
        5: "{region}: CDI {cdi} ({cdi_label}). SPI-3m {spi_3m:.2f}. Bodenfeuchte {soil_moisture_pct:.0f}% nFK. VHI {vhi:.1f}. Außerordentliche Lage.",
    },
    "bulletin": {
        0: "In {region} ist die Trockenheitslage normal. Der Kombinierte Dürreindex (CDI) beträgt {cdi} und zeigt keine Trockenheit an. Die Bodenfeuchte liegt bei {soil_moisture_pct:.0f}% der nutzbaren Feldkapazität.",
        1: "In {region} besteht eine leichte Trockenheit (CDI {cdi}). Die Niederschlagsmenge der letzten drei Monate liegt mit einem SPI-3m von {spi_3m:.2f} leicht unter dem langjährigen Mittel. Die Bodenfeuchte beträgt {soil_moisture_pct:.0f}% der nutzbaren Feldkapazität.",
        2: "In {region} besteht eine mäßige Trockenheit (CDI {cdi}). Der SPI-3m-Wert von {spi_3m:.2f} zeigt ein deutliches Niederschlagsdefizit. Die Bodenfeuchte liegt bei {soil_moisture_pct:.0f}% der nutzbaren Feldkapazität.",
        3: "In {region} herrscht eine schwere Trockenheit (CDI {cdi}). Der SPI-3m-Wert von {spi_3m:.2f} weist auf ein erhebliches Niederschlagsdefizit hin. Die Bodenfeuchte beträgt nur {soil_moisture_pct:.0f}% der nutzbaren Feldkapazität. Die Situation erfordert Aufmerksamkeit.",
        4: "In {region} herrscht eine extreme Trockenheit (CDI {cdi}). Der SPI-3m-Wert von {spi_3m:.2f} und eine Bodenfeuchte von {soil_moisture_pct:.0f}% nFK zeigen eine sehr ernste Lage. Maßnahmen zur Schadensminimierung sind zu prüfen.",
        5: "In {region} herrscht eine außerordentliche Trockenheit (CDI {cdi}). Dies ist eine sehr seltene Extremsituation. Alle verfügbaren Maßnahmen sollten geprüft werden.",
    },
}

ENTWICKLUNG_BLOCKS: dict[str, dict[int, str]] = {
    "behoerden": {
        0: "Trend: {trend_de}. Delta SPI-3m: {spi_3m_delta:+.2f}/Woche. Delta VHI: {vhi_delta:+.1f}.",
        1: "Trend: {trend_de}. Delta SPI-3m: {spi_3m_delta:+.2f}/Woche. Delta VHI: {vhi_delta:+.1f}.",
        2: "Trend: {trend_de}. Delta SPI-3m: {spi_3m_delta:+.2f}/Woche. Delta VHI: {vhi_delta:+.1f}.",
        3: "Trend: {trend_de}. Delta SPI-3m: {spi_3m_delta:+.2f}/Woche. Delta VHI: {vhi_delta:+.1f}. Lageentwicklung beobachten.",
        4: "Trend: {trend_de}. Delta SPI-3m: {spi_3m_delta:+.2f}/Woche. Delta VHI: {vhi_delta:+.1f}. Eskalation möglich.",
        5: "Trend: {trend_de}. Delta SPI-3m: {spi_3m_delta:+.2f}/Woche. Delta VHI: {vhi_delta:+.1f}. Situation kritisch überwachen.",
    },
    "bulletin": {
        0: "Die Situation in {region} ist stabil. Es sind keine wesentlichen Veränderungen gegenüber der Vorwoche festzustellen.",
        1: "Die Trockenheitslage in {region} hat sich {trend_de_bulletin}. Der SPI-3m-Wert hat sich um {spi_3m_delta:+.2f} verändert.",
        2: "Die Trockenheitslage in {region} hat sich {trend_de_bulletin}. Der Vegetationszustand (VHI) hat sich um {vhi_delta:+.1f} Punkte verändert.",
        3: "Die schwere Trockenheit in {region} hat sich {trend_de_bulletin}. Besondere Aufmerksamkeit ist für Landwirtschaft und Wasserversorgung geboten.",
        4: "Die extreme Trockenheit in {region} hat sich {trend_de_bulletin}. Der SPI-3m änderte sich um {spi_3m_delta:+.2f}. Sofortmaßnahmen könnten erforderlich sein.",
        5: "Die außerordentliche Trockenheit in {region} hält an. Alle verfügbaren Bewältigungskapazitäten sollten mobilisiert werden.",
    },
}

EINORDNUNG_BLOCKS: dict[str, dict[int, str]] = {
    "behoerden": {
        0: "Hist. Einordnung: {pct_critical_pct:.0f}% krit. Wochen (letzte 52 W.). SPI-3m im {spi_3m_percentile}. Perz. (Ref. 1961-2020). Keine Anomalie.",
        1: "Hist. Einordnung: {pct_critical_pct:.0f}% krit. Wochen (letzte 52 W.). SPI-3m im {spi_3m_percentile}. Perz. (Ref. 1961-2020).",
        2: "Hist. Einordnung: {pct_critical_pct:.0f}% krit. Wochen (letzte 52 W.). SPI-3m im {spi_3m_percentile}. Perz. (Ref. 1961-2020). Unter Median.",
        3: "Hist. Einordnung: {pct_critical_pct:.0f}% krit. Wochen (letzte 52 W.). SPI-3m im {spi_3m_percentile}. Perz. (Ref. 1961-2020). Seltene Situation.",
        4: "Hist. Einordnung: {pct_critical_pct:.0f}% krit. Wochen (letzte 52 W.). SPI-3m im {spi_3m_percentile}. Perz. (Ref. 1961-2020). Sehr seltene Extremlage.",
        5: "Hist. Einordnung: {pct_critical_pct:.0f}% krit. Wochen (letzte 52 W.). SPI-3m im {spi_3m_percentile}. Perz. (Ref. 1961-2020). Außerordentlich selten.",
    },
    "bulletin": {
        0: "Im Vergleich zum langjährigen Mittel (1961-2020) ist die aktuelle Situation in {region} normal. In den letzten 52 Wochen gab es {pct_critical_pct:.0f}% Wochen mit kritischer Trockenheit (CDI >= 3).",
        1: "Der SPI-3m-Wert liegt im {spi_3m_percentile}. Perzentil der Referenzperiode 1961-2020. In den letzten 52 Wochen waren {pct_critical_pct:.0f}% der Wochen kritisch.",
        2: "Der aktuelle SPI-3m-Wert liegt im {spi_3m_percentile}. Perzentil der Referenzperiode 1961-2020. In den letzten 52 Wochen waren {pct_critical_pct:.0f}% kritisch.",
        3: "Der SPI-3m-Wert befindet sich im {spi_3m_percentile}. Perzentil der Referenzperiode - eine seltene Situation. In den letzten 52 Wochen gab es {pct_critical_pct:.0f}% kritische Wochen.",
        4: "Der SPI-3m-Wert befindet sich im {spi_3m_percentile}. Perzentil der Referenzperiode - eine sehr seltene Extremsituation. {pct_critical_pct:.0f}% der letzten 52 Wochen waren kritisch.",
        5: "Der SPI-3m-Wert befindet sich im {spi_3m_percentile}. Perzentil der Referenzperiode - ausserordentlich selten. In {pct_critical_pct:.0f}% der letzten 52 Wochen herrschte kritische Trockenheit.",
    },
}

DATENGRUNDLAGE_BLOCKS: dict[str, str] = {
    "behoerden": (
        "Quelle: BAFU trockenheit.admin.ch. Datenstand: {data_timestamp}. "
        "Abdeckung: {coverage_pct:.0%}. Datenqualität: {overall}. "
        "Unsicherheiten: Werte basieren auf Modellberechnungen; lokale Abweichungen möglich."
    ),
    "bulletin": (
        "Die Daten stammen vom Bundesamt für Umwelt (BAFU), Quelle: trockenheit.admin.ch. "
        "Stand: {data_timestamp}. Datenabdeckung: {coverage_pct:.0%}. "
        "Die Werte basieren auf Messungen und Modellberechnungen; lokale Abweichungen sind möglich."
    ),
}
