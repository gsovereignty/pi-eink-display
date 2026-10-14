// Display Library for SPI e-paper panels from Dalian Good Display and boards from Waveshare.
// Requires HW SPI and Adafruit_GFX. Caution: these e-papers require 3.3V supply AND data lines!
//
// based on Demo Example from Good Display: http://www.e-paper-display.com/download_list/downloadcategoryid=34&isMode=false.html
//
// Author: Jean-Marc Zingg
//
// Version: see library.properties
//
// Library: https://github.com/ZinggJM/GxEPD2

#include "GxEPD2_2IC_EPD.h"

#if defined(ESP8266) || defined(ESP32)
#include <pgmspace.h>
#else
#include <avr/pgmspace.h>
#endif

GxEPD2_2IC_EPD::GxEPD2_2IC_EPD(int16_t cs, int16_t cs1, int16_t dc, int16_t rst, int16_t busy, int16_t busy_level, uint32_t busy_timeout,
                       uint16_t w, uint16_t h, GxEPD2::Panel p, bool c, bool pu, bool fpu) :
  WIDTH(w), HEIGHT(h), panel(p), hasColor(c), hasPartialUpdate(pu), hasFastPartialUpdate(fpu),
  _cs(cs), _cs1(cs1), _dc(dc), _rst(rst), _busy(busy), _busy_level(busy_level), _busy_timeout(busy_timeout), _diag_enabled(false),
  _pSPIx(&SPI), _spi_settings(4000000, MSBFIRST, SPI_MODE0)
{
  _initial_write = true;
  _initial_refresh = true;
  _power_is_on = false;
  _using_partial_mode = false;
  _hibernating = false;
  _reset_duration = 10;
  _busy_callback = 0;
  _busy_callback_parameter = 0;
}

void GxEPD2_2IC_EPD::csselect(uint8_t n, uint8_t m)
{
  if(m == 1)
  {
  	if (_cs >= 0) digitalWrite(_cs, n);
  }
  else if (m == 2)
  {
  	if (_cs1 >= 0) digitalWrite(_cs1, n);
  }
  else 
  {
  	if (_cs >= 0) digitalWrite(_cs, n);
  	if (_cs1 >= 0) digitalWrite(_cs1, n);
  }
}

void GxEPD2_2IC_EPD::init(uint32_t serial_diag_bitrate)
{
  init(serial_diag_bitrate, true, 10, false);
}

void GxEPD2_2IC_EPD::init(uint32_t serial_diag_bitrate, bool initial, uint16_t reset_duration, bool pulldown_rst_mode)
{
  _initial_write = initial;
  _initial_refresh = initial;
  _pulldown_rst_mode = pulldown_rst_mode;
  _power_is_on = false;
  _using_partial_mode = false;
  _hibernating = false;
  _reset_duration = reset_duration;
  if (serial_diag_bitrate > 0)
  {
    Serial.begin(serial_diag_bitrate);
    _diag_enabled = true;
  }
  if (_cs >= 0)
  {
    digitalWrite(_cs, HIGH);
    pinMode(_cs, OUTPUT);
  }
  if (_cs1 >= 0)
  {
    digitalWrite(_cs1, HIGH);
    pinMode(_cs1, OUTPUT);
  }
  if (_dc >= 0)
  {
    digitalWrite(_dc, HIGH);
    pinMode(_dc, OUTPUT);
  }
  _reset();
  if (_busy >= 0)
  {
    pinMode(_busy, INPUT);
  }
  _pSPIx->begin();
  if (_busy == MISO) // may be overridden, to be verified
  {
    pinMode(_busy, INPUT);
  }
  if (_dc == MISO) // may be overridden, TTGO T5 V2.66
  {
    pinMode(_dc, OUTPUT);
  }
}

void GxEPD2_2IC_EPD::setBusyCallback(void (*busyCallback)(const void*), const void* busy_callback_parameter)
{
  _busy_callback = busyCallback;
  _busy_callback_parameter = busy_callback_parameter;
}

void GxEPD2_2IC_EPD::selectSPI(SPIClass& spi, SPISettings spi_settings)
{
  _pSPIx = &spi;
  _spi_settings = spi_settings;
}

void GxEPD2_2IC_EPD::_reset()
{
  if (_rst >= 0)
  {
    if (_pulldown_rst_mode)
    {
      digitalWrite(_rst, LOW);
      pinMode(_rst, OUTPUT);
      delay(_reset_duration);
      pinMode(_rst, INPUT_PULLUP);
      delay(_reset_duration > 10 ? _reset_duration : 10);
    }
    else
    {
      digitalWrite(_rst, HIGH); // NEEDED for Waveshare "clever" reset circuit, power controller before reset pulse
      pinMode(_rst, OUTPUT);
      delay(10); // NEEDED for Waveshare "clever" reset circuit, at least delay(2);
      digitalWrite(_rst, LOW);
      delay(_reset_duration);
      digitalWrite(_rst, HIGH);
      delay(_reset_duration > 10 ? _reset_duration : 10);
    }
    _hibernating = false;
  }
}

void GxEPD2_2IC_EPD::_waitWhileBusy(const char* comment, uint16_t busy_time)
{
  if (_busy >= 0)
  {
    delay(1); // add some margin to become active
    unsigned long start = micros();
    while (1)
    {
      if (digitalRead(_busy) != _busy_level) break;
      if (_busy_callback) _busy_callback(_busy_callback_parameter);
      else delay(1);
      if (digitalRead(_busy) != _busy_level) break;
      if (micros() - start > _busy_timeout)
      {
        Serial.println("Busy Timeout!");
        break;
      }
#if defined(ESP8266) || defined(ESP32)
      yield(); // avoid wdt
#endif
    }
    if (comment)
    {
#if !defined(DISABLE_DIAGNOSTIC_OUTPUT)
      if (_diag_enabled)
      {
        unsigned long elapsed = micros() - start;
        Serial.print(comment);
        Serial.print(" : ");
        Serial.println(elapsed);
      }
#endif
    }
    (void) start;
  }
  else delay(busy_time);
}

void GxEPD2_2IC_EPD::_writeCommand(uint8_t c, uint8_t m)
{
  _pSPIx->beginTransaction(_spi_settings);
  if (_dc >= 0) digitalWrite(_dc, LOW);
  csselect(LOW,m);
  _pSPIx->transfer(c);
  csselect(HIGH,m);
  if (_dc >= 0) digitalWrite(_dc, HIGH);
  _pSPIx->endTransaction();
}

void GxEPD2_2IC_EPD::_writeData(uint8_t d, uint8_t m)
{
  _pSPIx->beginTransaction(_spi_settings);
  csselect(LOW,m);
  _pSPIx->transfer(d);
  csselect(HIGH,m);
  _pSPIx->endTransaction();
}

void GxEPD2_2IC_EPD::_writeData(const uint8_t* data, uint16_t n, uint8_t m)
{
  _pSPIx->beginTransaction(_spi_settings);
  csselect(LOW,m);
  for (uint16_t i = 0; i < n; i++)
  {
    _pSPIx->transfer(*data++);
  }
  csselect(HIGH,m);
  _pSPIx->endTransaction();
}

void GxEPD2_2IC_EPD::_writeDataPGM(const uint8_t* data, uint16_t n, int16_t fill_with_zeroes, uint8_t m)
{
  _pSPIx->beginTransaction(_spi_settings);
  csselect(LOW,m);
  for (uint16_t i = 0; i < n; i++)
  {
    _pSPIx->transfer(pgm_read_byte(&*data++));
  }
  while (fill_with_zeroes > 0)
  {
    _pSPIx->transfer(0x00);
    fill_with_zeroes--;
  }
  csselect(HIGH,m);
  _pSPIx->endTransaction();
}

void GxEPD2_2IC_EPD::_writeDataPGM_sCS(const uint8_t* data, uint16_t n, int16_t fill_with_zeroes, uint8_t m)
{
  _pSPIx->beginTransaction(_spi_settings);
  for (uint8_t i = 0; i < n; i++)
  {
    csselect(LOW,m);
    _pSPIx->transfer(pgm_read_byte(&*data++));
    csselect(HIGH,m);
  }
  while (fill_with_zeroes > 0)
  {
    csselect(LOW,m);
    _pSPIx->transfer(0x00);
    fill_with_zeroes--;
    csselect(HIGH,m);
  }
  _pSPIx->endTransaction();
}

void GxEPD2_2IC_EPD::_writeCommandData(const uint8_t* pCommandData, uint8_t datalen, uint8_t m)
{
  _pSPIx->beginTransaction(_spi_settings);
  if (_dc >= 0) digitalWrite(_dc, LOW);
  csselect(LOW,m);
  _pSPIx->transfer(*pCommandData++);
  if (_dc >= 0) digitalWrite(_dc, HIGH);
  for (uint8_t i = 0; i < datalen - 1; i++)  // sub the command
  {
    _pSPIx->transfer(*pCommandData++);
  }
  csselect(HIGH,m);
  _pSPIx->endTransaction();
}

void GxEPD2_2IC_EPD::_writeCommandDataPGM(const uint8_t* pCommandData, uint8_t datalen, uint8_t m)
{
  _pSPIx->beginTransaction(_spi_settings);
  if (_dc >= 0) digitalWrite(_dc, LOW);
  csselect(LOW,m);
  _pSPIx->transfer(pgm_read_byte(&*pCommandData++));
  if (_dc >= 0) digitalWrite(_dc, HIGH);
  for (uint8_t i = 0; i < datalen - 1; i++)  // sub the command
  {
    _pSPIx->transfer(pgm_read_byte(&*pCommandData++));
  }
  csselect(HIGH,m);
  _pSPIx->endTransaction();
}

void GxEPD2_2IC_EPD::_startTransfer(uint8_t m)
{
  _pSPIx->beginTransaction(_spi_settings);
  csselect(LOW,m);
}

void GxEPD2_2IC_EPD::_transfer(uint8_t value)
{
  _pSPIx->transfer(value);
}

void GxEPD2_2IC_EPD::_endTransfer(uint8_t m)
{
  csselect(HIGH,m);
  _pSPIx->endTransaction();
}
