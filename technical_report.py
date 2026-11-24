# -*- coding: utf-8 -*-
"""GeoReport | Five-page English territorial diagnostics report generator."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Paragraph


# Report palette matches the GeoReport cartographic layout.
VERDE = colors.HexColor('#205747')
VERDE_ESCURO = colors.HexColor('#153D32')
VERDE_CLARO = colors.HexColor('#EAF4EE')
VERDE_MEDIO = colors.HexColor('#79BC95')
TEXTO = colors.HexColor('#1E2A26')
SECUNDARIO = colors.HexColor('#5F726B')
LINHA = colors.HexColor('#DCE5DF')
FUNDO = colors.HexColor('#F6F9F7')
BRANCO = colors.white
LARANJA = colors.HexColor('#D77A56')

# Use the same MapBiomas colors as the map.
CORES_CLASSES = {
    3: '#1f8d49', 4: '#7dc975', 9: '#7a5900',
    11: '#519799', 12: '#d6bc74', 15: '#edde8e',
    19: '#C27BA0', 21: '#ffefc3', 24: '#d4271e',
    25: '#db4d4f', 30: '#9c0027', 31: '#091077',
    33: '#2532e4', 36: '#d082de', 5: '#04381d',
    6: '#007785', 7: '#228c70', 23: '#ffa07a',
    29: '#ad5100', 32: '#fc8114', 49: '#02d659',
    50: '#ffaa5f', 75: '#757272', 77: '#86b074',
    84: '#81dbbf', 91: '#403d3e',
}




REPORT_CLASS_NAMES = {
    3: "Forest formation", 4: "Savanna formation", 9: "Forest plantation",
    11: "Wetland", 12: "Grassland", 15: "Pasture",
    19: "Temporary cropland", 21: "Mosaic of uses",
    24: "Urban area", 25: "Other non-vegetated areas",
    30: "Mining", 31: "Aquaculture", 33: "River, lake and ocean",
    36: "Perennial cropland", 5: "Mangrove", 6: "Flooded forest",
    7: "Flooded savanna", 23: "Beach, dune and sand",
    29: "Rocky outcrop", 32: "Salt flat", 49: "Wooded restinga",
    50: "Herbaceous/shrubby restinga", 75: "Solar power plant",
    77: "Herbaceous-shrub formation", 84: "Salt marsh", 91: "Wind farm",
}

REPORT_LABELS = {'header': 'TERRITORIAL DIAGNOSTICS',
 'page': 'Page',
 'cover_kicker': 'GEOREPORT / TECHNICAL REPORT',
 'cover_line_1': 'TERRITORIAL',
 'cover_line_2': 'DIAGNOSTICS',
 'theme': 'Land use and land cover',
 'thematic_year': 'Classification year',
 'generated_on': 'Report generated on',
 'indicators': 'KEY INDICATORS',
 'vector_area': 'VECTOR AREA',
 'classified_area': 'CLASSIFIED AREA',
 'classes_present': 'CLASSES PRESENT',
 'location': 'STATE / LOCATION',
 'not_available': 'Not specified',
 'thematic_map': '01 | THEMATIC MAP',
 'table': '02 | AREA BY CLASS',
 'chart': '03 | CLASS DISTRIBUTION',
 'summary': '04 | SUMMARY AND METHODOLOGY',
 'classes_identified': 'Classes identified',
 'raster_vector_ratio': 'Raster / vector ratio',
 'class': 'Class',
 'area_km2': 'Area (km²)',
 'area_ha': 'Area (ha)',
 'percentage': 'Percentage',
 'pixels': 'Pixels',
 'table_note': 'Approximate pixel-based area; percentages are calculated relative to the '
               'classified area.',
 'other_classes': 'Other classes',
 'chart_note': 'Percentages are relative to classified pixels, not the total area of the polygon.',
 'findings': 'INTERPRETATION OF RESULTS',
 'methods': 'METHOD SUMMARY',
 'limitations': 'ANALYSIS LIMITATIONS',
 'sources': 'SOURCES AND TRACEABILITY',
 'method1': '1. Read and validate the supplied vector boundary.',
 'method2': '2. Harmonize coordinate reference systems and clip the MapBiomas raster.',
 'method3': '3. Count classified pixels and calculate area by class.',
 'method4': '4. Automatically generate the map, CSV table and this report.',
 'limitation1': 'Areas were estimated from whole pixels; boundaries, resolution and reprojection '
                'may cause differences from the vector area.',
 'limitation2': 'Thematic classification was not field-validated for this report. This is a '
                'single-year snapshot, not a land-cover change analysis.'}



def _report_label(language, key):
    """Report label."""
    return REPORT_LABELS[key]



def _class_name(row, language="en"):
    """Class name."""
    class_code = int(row["Class_ID"])
    return REPORT_CLASS_NAMES.get(class_code, f"Class {class_code}")




def _register_fonts():
    """Register fonts."""
    fontes = [
        ('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
         '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'),
        ('C:/Windows/Fonts/arial.ttf', 'C:/Windows/Fonts/arialbd.ttf'),
        ('C:/Windows/Fonts/calibri.ttf', 'C:/Windows/Fonts/calibrib.ttf'),
    ]
    for regular, negrito in fontes:
        if Path(regular).is_file() and Path(negrito).is_file():
            if 'GeoRegular' not in pdfmetrics.getRegisteredFontNames():
                pdfmetrics.registerFont(TTFont('GeoRegular', regular))
                pdfmetrics.registerFont(TTFont('GeoBold', negrito))
            return 'GeoRegular', 'GeoBold'
    # Fallback fonts support the Latin-1 character set.
    return 'Helvetica', 'Helvetica-Bold'


def _format_number(value, decimals=2, language="en"):
    """Format number."""
    return f"{float(value):,.{decimals}f}"



def _format_integer(value, language="en"):
    """Format integer."""
    return f"{int(value):,}"



def _draw_text(c, x, y, s, fonte='GeoRegular', tamanho=10, color=TEXTO):
    fonte = fonte if fonte in pdfmetrics.getRegisteredFontNames() else (
        'Helvetica-Bold' if fonte == 'GeoBold' else 'Helvetica'
    )
    c.setFont(fonte, tamanho)
    c.setFillColor(color)
    c.drawString(x, y, str(s))


def _draw_right_text(c, x, y, s, fonte='GeoRegular', tamanho=10, color=TEXTO):
    fonte = fonte if fonte in pdfmetrics.getRegisteredFontNames() else (
        'Helvetica-Bold' if fonte == 'GeoBold' else 'Helvetica'
    )
    c.setFont(fonte, tamanho)
    c.setFillColor(color)
    c.drawRightString(x, y, str(s))


def _draw_paragraph(c, text, x, topo, largura, tamanho=10, entrelinha=15,
                color=TEXTO, negrito=False, limite_altura=None):
    estilo = ParagraphStyle(
        name='GeoBody',
        fontName=('GeoBold' if negrito else 'GeoRegular')
        if 'GeoRegular' in pdfmetrics.getRegisteredFontNames()
        else ('Helvetica-Bold' if negrito else 'Helvetica'),
        fontSize=tamanho, leading=entrelinha, textColor=color,
        spaceBefore=0, spaceAfter=0,
    )
    bloco = Paragraph(escape(str(text)), estilo)
    _, altura = bloco.wrap(largura, 1000)
    if limite_altura is not None and altura > limite_altura:
        raise ValueError(f'Texto muito extenso para o layout: {str(text)[:70]}')
    bloco.drawOn(c, x, topo - altura)
    return topo - altura


def _page_header(c, numero, title, area, year, W, H, language):
    c.setFillColor(VERDE_ESCURO)
    c.rect(0, H - 8, W, 8, fill=1, stroke=0)
    _draw_text(c, 47, H - 37, 'GEOREPORT', 'GeoBold', 13, VERDE)
    _draw_right_text(c, W - 47, H - 36,
               f'{_report_label(language, "header")}  |  {year}',
               'GeoRegular', 8.4, SECUNDARIO)
    c.setStrokeColor(LINHA)
    c.line(47, H - 48, W - 47, H - 48)
    _draw_text(c, 47, H - 87, title, 'GeoBold', 19, VERDE_ESCURO)
    _draw_paragraph(c, area, 47, H - 98, W - 94, 9.4, 12, SECUNDARIO, limite_altura=26)
    _page_footer(c, numero, area, W, language)


def _page_footer(c, numero, area, W, language):
    c.setStrokeColor(LINHA)
    c.line(47, 39, W - 47, 39)
    rotulo = f'GeoReport | {area}'
    if len(rotulo) > 72:
        rotulo = rotulo[:69] + '...'
    _draw_text(c, 47, 23, rotulo, 'GeoRegular', 8, SECUNDARIO)
    _draw_right_text(c, W - 47, 23, f'{_report_label(language, "page")} {numero} / 5',
               'GeoRegular', 8, SECUNDARIO)


def _metric_card(c, x, y, w, h, rotulo, value, tamanho=15):
    c.setFillColor(VERDE_CLARO)
    c.setStrokeColor(LINHA)
    c.roundRect(x, y, w, h, 10, fill=1, stroke=1)
    _draw_text(c, x + 14, y + h - 21, rotulo.upper(), 'GeoBold', 8.5, SECUNDARIO)
    _draw_paragraph(c, value, x + 14, y + h - 29, w - 28,
               tamanho, tamanho + 5, VERDE_ESCURO, True,
               limite_altura=h - 35)


def _cover_page(c, W, H, data):
    language = data['language']
    c.setFillColor(VERDE_ESCURO)
    c.rect(0, 0, W, H, stroke=0, fill=1)
    c.setFillColor(VERDE_MEDIO)
    c.rect(0, H - 11, W, 11, stroke=0, fill=1)
    c.setFillColor(colors.HexColor('#2C6653'))
    c.roundRect(490, 100, 295, 394, 22, stroke=0, fill=1)
    _draw_text(c, 56, H - 66, _report_label(language, 'cover_kicker'),
           'GeoBold', 12, colors.HexColor('#B6D9C5'))
    _draw_text(c, 56, H - 148, _report_label(language, 'cover_line_1'), 'GeoBold', 31, BRANCO)
    _draw_text(c, 56, H - 191, _report_label(language, 'cover_line_2'), 'GeoBold', 31, BRANCO)
    _draw_text(c, 56, H - 234, _report_label(language, 'theme'),
           'GeoRegular', 15, colors.HexColor('#CDE3D6'))
    c.setStrokeColor(colors.HexColor('#5F947D'))
    c.line(56, H - 263, 448, H - 263)
    _draw_paragraph(c, data['area'], 56, H - 290, 382,
               tamanho=18, entrelinha=26, color=BRANCO,
               negrito=True, limite_altura=92)
    _draw_text(c, 56, 78, f'{_report_label(language, "thematic_year")}: {data["year"]}',
           'GeoRegular', 11, colors.HexColor('#DDEFE5'))
    _draw_text(c, 56, 58, f'{_report_label(language, "generated_on")} {data["date_generated"]}',
           'GeoRegular', 9, colors.HexColor('#DDEFE5'))
    _draw_text(c, 515, 452, _report_label(language, 'indicators'), 'GeoBold', 13, BRANCO)
    indicadores = [
        (_report_label(language, 'vector_area'), f'{_format_number(data["vector_area"], language=language)} km²'),
        (_report_label(language, 'classified_area'), f'{_format_number(data["classified_area"], language=language)} km²'),
        (_report_label(language, 'classes_present'), str(data['classes'])),
        (_report_label(language, 'location'), data['states'] or _report_label(language, 'not_available')),
    ]
    y = 417
    for rotulo, value in indicadores:
        _draw_text(c, 515, y, rotulo, 'GeoBold', 8.2,
               colors.HexColor('#C8E3D4'))
        _draw_paragraph(c, value, 515, y - 9, 250,
                   13.2, 18, BRANCO, True, limite_altura=30)
        y -= 78
    _draw_text(c, 515, 113, 'GEOREPORT - IVANA BEZERRA',
           'GeoBold', 8.5, colors.HexColor('#D5EADE'))
    c.showPage()


def _map_page(c, W, H, data, map_path):
    language = data['language']
    _page_header(c, 2, _report_label(language, 'thematic_map'), data['area'], data['year'], W, H, language)
    c.setStrokeColor(LINHA)
    c.setFillColor(colors.white)
    bx, by, bw, bh = 47, 92, W - 94, 357
    c.roundRect(bx, by, bw, bh, 8, fill=1, stroke=1)
    img = ImageReader(str(map_path))
    iw, ih = img.getSize()
    if iw <= 0 or ih <= 0:
        raise ValueError('The map PNG has invalid dimensions.')
    maxw, maxh = bw - 22, bh - 18
    fator = min(maxw / iw, maxh / ih)
    dw, dh = iw * fator, ih * fator
    c.drawImage(img, bx + (bw - dw) / 2, by + (bh - dh) / 2,
                width=dw, height=dh, preserveAspectRatio=True, mask='auto')
    legenda = (
        f'Figure 1. Automatically generated thematic map for {data["area"]}. '
        f'MapBiomas classification for {data["year"]}; CRS: {data["crs"]}.'
        if language == 'en' else
        f'Figura 1. Mapa temático automatizado para {data["area"]}. '
        f'Classificação MapBiomas {data["year"]}; CRS: {data["crs"]}.'
    )
    _draw_paragraph(c, legenda, 47, 83, W - 94, 8.4, 11, SECUNDARIO, limite_altura=23)
    c.showPage()


def _table_page(c, W, H, data, table):
    language = data['language']
    _page_header(c, 3, _report_label(language, 'table'), data['area'], data['year'], W, H, language)
    _metric_card(c, 47, 408, 230, 55, _report_label(language, 'classified_area'),
            f'{_format_number(data["classified_area"], language=language)} km²', 14)
    _metric_card(c, 290, 408, 230, 55, _report_label(language, 'classes_identified'),
            str(data['classes']), 14)
    _metric_card(c, 534, 408, 260, 55, _report_label(language, 'raster_vector_ratio'),
            f'{_format_number(data["coverage"], language=language)} %', 14)
    left, right = 47, W - 47
    top = 386
    cols = [left, 118, 430, 547, 648, 733, right]
    headers = ['ID', _report_label(language, 'class'), _report_label(language, 'area_km2'),
               _report_label(language, 'area_ha'), _report_label(language, 'percentage'), _report_label(language, 'pixels')]
    c.setFillColor(VERDE)
    c.rect(left, top - 25, right - left, 29, fill=1, stroke=0)
    for i, header in enumerate(headers):
        xx = cols[i] + 7 if i in (0, 1) else cols[i + 1] - 7
        if i in (0, 1):
            _draw_text(c, xx, top - 16, header, 'GeoBold', 8.4, BRANCO)
        else:
            _draw_right_text(c, xx, top - 16, header, 'GeoBold', 8.4, BRANCO)
    numero = len(table)
    altura_linha = min(23, 280 / max(1, numero))
    y = top - 25
    fonte = 8.7 if numero <= 17 else 7.3
    for n, (_, row) in enumerate(table.iterrows()):
        fundo = colors.white if n % 2 == 0 else FUNDO
        c.setFillColor(fundo)
        c.rect(left, y - altura_linha, right - left, altura_linha,
               stroke=0, fill=1)
        class_code = int(row['Class_ID'])
        campos = [str(class_code), _class_name(row, language),
                  _format_number(row['Area_km2'], 4, language),
                  _format_number(row['Area_km2'] * 100, 2, language),
                  f'{_format_number(row["Percentage"], 2, language)}%',
                  _format_integer(row['Pixels'], language)]
        largura_classe = cols[2] - cols[1] - 18
        max_char = max(28, int(largura_classe / (fonte * 0.53)))
        if len(campos[1]) > max_char:
            campos[1] = campos[1][:max_char - 1] + '…'
        for i, value in enumerate(campos):
            xx = cols[i] + 7 if i in (0, 1) else cols[i + 1] - 7
            if i in (0, 1):
                _draw_text(c, xx, y - altura_linha + (altura_linha - fonte) / 2 + 1,
                       value, 'GeoRegular', fonte)
            else:
                _draw_right_text(c, xx, y - altura_linha + (altura_linha - fonte) / 2 + 1,
                           value, 'GeoRegular', fonte)
        y -= altura_linha
    if y < 65:
        raise ValueError('The table exceeds the page height; reduce or paginate class entries.')
    _draw_text(c, 47, max(58, y - 19), _report_label(language, 'table_note'),
           'GeoRegular', 8, SECUNDARIO)
    c.showPage()


def _chart_page(c, W, H, data, table):
    language = data['language']
    _page_header(c, 4, _report_label(language, 'chart'), data['area'], data['year'], W, H, language)
    barras = [(_class_name(row, language), float(row['Percentage']),
               int(row['Class_ID'])) for _, row in table.head(10).iterrows()]
    if len(table) > 10:
        restante = float(table.iloc[10:]['Percentage'].sum())
        barras.append((_report_label(language, 'other_classes'), restante, None))
    n = len(barras)
    topo, inferior = 432, 112
    passo = min(30, (topo - inferior) / max(1, n))
    x_label, x_inicio, comprimento_max = 54, 312, 336
    maximo = max(1, max(v for _, v, _ in barras))
    for i, (name, value, class_code) in enumerate(barras):
        y = topo - i * passo
        if len(name) > 30:
            name = name[:29] + '…'
        _draw_text(c, x_label, y, name, 'GeoRegular', 9.2, TEXTO)
        c.setFillColor(FUNDO)
        c.roundRect(x_inicio, y - 3, comprimento_max, 12, 4, fill=1, stroke=0)
        c.setFillColor(colors.HexColor(CORES_CLASSES.get(class_code, '#92ADA0')))
        c.roundRect(x_inicio, y - 3,
                    max(1.4, comprimento_max * value / maximo),
                    12, 4, fill=1, stroke=0)
        _draw_right_text(c, 728, y - 1, f'{_format_number(value, 1, language)}%',
                   'GeoBold', 9.4, VERDE_ESCURO)
    _draw_text(c, 54, 78, _report_label(language, 'chart_note'),
           'GeoRegular', 8.1, SECUNDARIO)
    c.showPage()


def _section(c, x, y, title, textos, largura):
    _draw_text(c, x, y, title, 'GeoBold', 12, VERDE)
    cy = y - 19
    for text in textos:
        cy = _draw_paragraph(c, text, x, cy, largura, 9.8, 14.5,
                        TEXTO, limite_altura=80) - 9
    return cy


def _summary_page(c, W, H, data, table):
    language = data['language']
    _page_header(c, 5, _report_label(language, 'summary'), data['area'], data['year'], W, H, language)
    primeira = table.iloc[0]
    top2 = table.head(2)['Percentage'].sum()
    texto_analise = [
        f'The largest class is {_class_name(primeira, language)}, covering '
        f'{_format_number(primeira["Area_km2"], language=language)} km² '
        f'({_format_number(primeira["Percentage"], 1, language)}% of the classified area).',
        f'The two largest classes together account for '
        f'{_format_number(top2, 1, language)}% of the classified area.',
        f'{data["classes"]} classes were identified, with a total classified '
        f'area of {_format_number(data["classified_area"], language=language)} km².',
    ]
    fontes = [
        f'Land use and land cover: MapBiomas, Collection 4 (10 m), year {data["year"]}.',
        f'Geographic boundary: {data["area"]} (user-supplied vector file).',
        f'Analysis CRS: {data["crs"]}. Prepared by: GEOREPORT - IVANA BEZERRA.',
    ]
    margem, xdir, largura = 47, 443, 337
    _section(c, margem, 453, _report_label(language, 'findings'), texto_analise, 346)
    _section(c, xdir, 453, _report_label(language, 'methods'),
           [_report_label(language, f'method{i}') for i in range(1, 5)], largura)
    _section(c, margem, 232, _report_label(language, 'limitations'),
           [_report_label(language, 'limitation1'), _report_label(language, 'limitation2')], 346)
    _section(c, xdir, 221, _report_label(language, 'sources'), fontes, largura)
    c.showPage()


def generate_technical_report(
    map_path,
    table_path,
    output_dir,
    area_name,
    vector_area_km2,
    crs,
    year=2025,
    states=None,
    language='en',
):
    """Generate a five-page English technical report from map and CSV."""
    _report_label(language, 'theme')  
    map_path = Path(map_path)
    table_path = Path(table_path)
    output_dir = Path(output_dir)
    if not map_path.is_file():
        raise FileNotFoundError(f'Map PNG not found: {map_path}')
    if not table_path.is_file():
        raise FileNotFoundError(f'Class statistics CSV not found: {table_path}')
    table = pd.read_csv(table_path, encoding='utf-8-sig')
    exigidas = {'Class_ID', 'Class', 'Area_km2'}
    if not exigidas.issubset(table.columns):
        raise ValueError('CSV is missing columns: ' + ', '.join(sorted(exigidas - set(table.columns))))
    if table.empty or table['Class'].isna().any():
        raise ValueError('The class statistics table is empty or contains missing class names.')
    for coluna in ('Area_km2', 'Pixels', 'Class_ID'):
        if coluna in table.columns:
            table[coluna] = pd.to_numeric(table[coluna], errors='raise')
    if table['Area_km2'].isna().any() or (table['Area_km2'] < 0).any():
        raise ValueError('The CSV contains invalid area values.')
    soma = float(table['Area_km2'].sum())
    vector_area_km2 = float(vector_area_km2)
    if soma <= 0 or vector_area_km2 <= 0:
        raise ValueError('Classified and vector areas must be positive.')
    table['Percentage'] = table['Area_km2'] / soma * 100
    table = table.sort_values('Area_km2', ascending=False).reset_index(drop=True)
    if len(table) > 27:
        raise ValueError('More than 27 classes: PDF table pagination is required.')
    if 'Pixels' not in table.columns:
        table['Pixels'] = 0
    table['Class_ID'] = table['Class_ID'].astype(int)

    output_dir.mkdir(parents=True, exist_ok=True)
    file_path = output_dir / 'territorial_diagnostics_report.pdf'
    _register_fonts()
    W, H = landscape(A4)
    data = {
        'area': str(area_name),
        'year': int(year),
        'vector_area': vector_area_km2,
        'classified_area': soma,
        'classes': len(table),
        'coverage': soma / vector_area_km2 * 100,
        'states': ' / '.join(states) if states else '',
        'crs': str(crs),
        'date_generated': datetime.now().strftime('%Y-%m-%d'),
        'language': language,
    }
    c = canvas.Canvas(str(file_path), pagesize=(W, H), pageCompression=1)
    c.setTitle(f'GeoReport | {_report_label(language, "header")} | {area_name}')
    c.setAuthor('GEOREPORT - IVANA BEZERRA')
    c.setSubject(f'{_report_label(language, "theme")} | {year}')
    _cover_page(c, W, H, data)
    _map_page(c, W, H, data, map_path)
    _table_page(c, W, H, data, table)
    _chart_page(c, W, H, data, table)
    _summary_page(c, W, H, data, table)
    c.save()
    print(f'Technical report ({language.upper()}):', file_path)
    return file_path


if __name__ == '__main__':
    print('This module is imported by GeoReport main.py.')
    print('For a standalone test, import generate_technical_report and supply the map, CSV and metadata.')
