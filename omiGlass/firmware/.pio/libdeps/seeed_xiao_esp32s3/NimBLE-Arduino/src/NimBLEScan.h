/*
 * NimBLEScan.h
 *
 *  Created: on Jan 24 2020
 *      Author H2zero
 *
 * Originally:
 *
 * BLEScan.h
 *
 *  Created on: Jul 1, 2017
 *      Author: kolban
 */
#ifndef COMPONENTS_NIMBLE_SCAN_H_
#define COMPONENTS_NIMBLE_SCAN_H_

#include "nimconfig.h"
#if defined(CONFIG_BT_ENABLED) && defined(CONFIG_BT_NIMBLE_ROLE_OBSERVER)

#include "NimBLEAdvertisedDevice.h"
#include "NimBLEUtils.h"

#if defined(CONFIG_NIMBLE_CPP_IDF)
#include "host/ble_gap.h"
#else
#include "nimble/nimble/host/include/host/ble_gap.h"
#endif

#include <vector>

class NimBLEDevice;
class NimBLEScan;
class NimBLEAdvertisedDevice;
class NimBLEAdvertisedDeviceCallbacks;
class NimBLEAddress;

/**
 * @brief A class that contains and operates on the results of a BLE scan.
 * @details When a scan completes, we have a set of found devices.  Each device is described
 * by a NimBLEAdvertisedDevice object.  The number of items in the set is given by
 * getCount().  We can retrieve a device by calling getDevice() passing in the
 * index (starting at 0) of the desired device.
 */
class NimBLEScanResults {
public:
    void                                           dump();
    int                                            getCount();
    NimBLEAdvertisedDevice                         getDevice(uint32_t i);
    std::vector<NimBLEAdvertisedDevice*>::iterator begin();
    std::vector<NimBLEAdvertisedDevice*>::iterator end();
    NimBLEAdvertisedDevice                         *getDevice(const NimBLEAddress &address);

private:
    friend NimBLEScan;
    std::vector<NimBLEAdvertisedDevice*> m_advertisedDevicesVector;
};

/**
 * @brief Perform and manage %BLE scans.
 *
 * Scanning is associated with a %BLE client that is attempting to locate BLE servers.
 */
class NimBLEScan {
public:
    bool                start(uint32_t duration, void (*scanCompleteCB)(NimBLEScanResults), bool is_continue = false);
    NimBLEScanResults   start(uint32_t duration, bool is_continue = false);
    bool                isScanning();
    void                setAdvertisedDeviceCallbacks(NimBLEAdvertisedDeviceCallbacks* pAdvertisedDeviceCallbacks, bool wantDuplicates = false);
    void                setActiveScan(bool active);
    void                setInterval(uint16_t intervalMSecs);
    void                setWindow(uint16_t windowMSecs);
    void                setDuplicateFilter(bool enabled);
    void                setLimitedOnly(bool enabled);
    void                setFilterPolicy(uint8_t filter);
    void                clearDuplicateCache();
    bool                stop();
    void                clearResults();
    NimBLEScanResults   getResults();
    void                setMaxResults(uint8_t maxResults);
    void                erase(const NimBLEAddress &address);


private:
    friend class NimBLEDevice;

    NimBLEScan();
    ~NimBLEScan();
    static int          handleGapEvent(ble_gap_event*  event, void* arg);
    void                onHostReset();
    void                onHostSync();

    NimBLEAdvertisedDeviceCallbacks*    m_pAdvertisedDeviceCallbacks = nullptr;
    void                                (*m_scanCompleteCB)(NimBLEScanResults scanResults);
    ble_gap_disc_params                 m_scan_params;
    bool                                m_ignoreResults;
    NimBLEScanResults                   m_scanResults;
    uint32_t                            m_duration;
    ble_task_data_t                     *m_pTaskData;
    uint8_t                             m_maxResults;
};

#endif /* CONFIG_BT_ENABLED CONFIG_BT_NIMBLE_ROLE_OBSERVER */
#endif /* COMPONENTS_NIMBLE_SCAN_H_ */
