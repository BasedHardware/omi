/*
 * NimBLEServer.h
 *
 *  Created: on March 2, 2020
 *      Author H2zero
 *
 * Originally:
 *
 * BLEServer.h
 *
 *  Created on: Apr 16, 2017
 *      Author: kolban
 */

#ifndef MAIN_NIMBLESERVER_H_
#define MAIN_NIMBLESERVER_H_

#include "nimconfig.h"
#if defined(CONFIG_BT_ENABLED) && defined(CONFIG_BT_NIMBLE_ROLE_PERIPHERAL)

#define NIMBLE_ATT_REMOVE_HIDE 1
#define NIMBLE_ATT_REMOVE_DELETE 2

#define onMtuChanged onMTUChange

#include "NimBLEUtils.h"
#include "NimBLEAddress.h"
#if CONFIG_BT_NIMBLE_EXT_ADV
#include "NimBLEExtAdvertising.h"
#else
#include "NimBLEAdvertising.h"
#endif
#include "NimBLEService.h"
#include "NimBLESecurity.h"
#include "NimBLEConnInfo.h"


class NimBLEService;
class NimBLECharacteristic;
class NimBLEServerCallbacks;


/**
 * @brief The model of a %BLE server.
 */
class NimBLEServer {
public:
    size_t                 getConnectedCount();
    NimBLEService*         createService(const char* uuid);
    NimBLEService*         createService(const NimBLEUUID &uuid);
    void                   removeService(NimBLEService* service, bool deleteSvc = false);
    void                   addService(NimBLEService* service);
    void                   setCallbacks(NimBLEServerCallbacks* pCallbacks,
                                        bool deleteCallbacks = true);
#if CONFIG_BT_NIMBLE_EXT_ADV
    NimBLEExtAdvertising*  getAdvertising();
    bool                   startAdvertising(uint8_t inst_id,
                                            int duration = 0,
                                            int max_events = 0);
    bool                   stopAdvertising(uint8_t inst_id);
#endif
#if !CONFIG_BT_NIMBLE_EXT_ADV || defined(_DOXYGEN_)
    NimBLEAdvertising*     getAdvertising();
    bool                   startAdvertising();
#endif
    bool                   stopAdvertising();
    void                   start();
    NimBLEService*         getServiceByUUID(const char* uuid, uint16_t instanceId = 0);
    NimBLEService*         getServiceByUUID(const NimBLEUUID &uuid, uint16_t instanceId = 0);
    NimBLEService*         getServiceByHandle(uint16_t handle);
    int                    disconnect(uint16_t connID,
                                      uint8_t reason = BLE_ERR_REM_USER_CONN_TERM);
    void                   updateConnParams(uint16_t conn_handle,
                                            uint16_t minInterval, uint16_t maxInterval,
                                            uint16_t latency, uint16_t timeout);
    void                   setDataLen(uint16_t conn_handle, uint16_t tx_octets);
    uint16_t               getPeerMTU(uint16_t conn_id);
    std::vector<uint16_t>  getPeerDevices();
    NimBLEConnInfo         getPeerInfo(size_t index);
    NimBLEConnInfo         getPeerInfo(const NimBLEAddress& address);
    NimBLEConnInfo         getPeerIDInfo(uint16_t id);
#if !CONFIG_BT_NIMBLE_EXT_ADV || defined(_DOXYGEN_)
    void                   advertiseOnDisconnect(bool);
#endif

private:
    NimBLEServer();
    ~NimBLEServer();
    friend class           NimBLECharacteristic;
    friend class           NimBLEService;
    friend class           NimBLEDevice;
    friend class           NimBLEAdvertising;
#if CONFIG_BT_NIMBLE_EXT_ADV
    friend class           NimBLEExtAdvertising;
    friend class           NimBLEExtAdvertisementData;
#endif

    bool                   m_gattsStarted;
#if !CONFIG_BT_NIMBLE_EXT_ADV
    bool                   m_advertiseOnDisconnect;
#endif
    bool                   m_svcChanged;
    NimBLEServerCallbacks* m_pServerCallbacks;
    bool                   m_deleteCallbacks;
    uint16_t               m_indWait[CONFIG_BT_NIMBLE_MAX_CONNECTIONS];
    std::vector<uint16_t>  m_connectedPeersVec;

//    uint16_t               m_svcChgChrHdl; // Future use

    std::vector<NimBLEService*> m_svcVec;
    std::vector<NimBLECharacteristic*> m_notifyChrVec;

    static int             handleGapEvent(struct ble_gap_event *event, void *arg);
    void                   serviceChanged();
    void                   resetGATT();
    bool                   setIndicateWait(uint16_t conn_handle);
    void                   clearIndicateWait(uint16_t conn_handle);
}; // NimBLEServer


/**
 * @brief Callbacks associated with the operation of a %BLE server.
 */
class NimBLEServerCallbacks {
public:
    virtual ~NimBLEServerCallbacks() {};

    /**
     * @brief Handle a client connection.
     * This is called when a client connects.
     * @param [in] pServer A pointer to the %BLE server that received the client connection.
     */
    virtual void onConnect(NimBLEServer* pServer);

    /**
     * @brief Handle a client connection.
     * This is called when a client connects.
     * @param [in] pServer A pointer to the %BLE server that received the client connection.
     * @param [in] desc A pointer to the connection description structure containig information
     * about the connection parameters.
     */
    virtual void onConnect(NimBLEServer* pServer, ble_gap_conn_desc* desc);

    /**
     * @brief Handle a client disconnection.
     * This is called when a client disconnects.
     * @param [in] pServer A reference to the %BLE server that received the existing client disconnection.
     */
    virtual void onDisconnect(NimBLEServer* pServer);

     /**
     * @brief Handle a client disconnection.
     * This is called when a client discconnects.
     * @param [in] pServer A pointer to the %BLE server that received the client disconnection.
     * @param [in] desc A pointer to the connection description structure containing information
     * about the connection.
     */
    virtual void onDisconnect(NimBLEServer* pServer, ble_gap_conn_desc* desc);

     /**
     * @brief Called when the connection MTU changes.
     * @param [in] MTU The new MTU value.
     * @param [in] desc A pointer to the connection description structure containing information
     * about the connection.
     */
    virtual void onMTUChange(uint16_t MTU, ble_gap_conn_desc* desc);

    /**
     * @brief Called when a client requests a passkey for pairing.
     * @return The passkey to be sent to the client.
     */
    virtual uint32_t onPassKeyRequest();

    //virtual void onPassKeyNotify(uint32_t pass_key);
    //virtual bool onSecurityRequest();

    /**
     * @brief Called when the pairing procedure is complete.
     * @param [in] desc A pointer to the struct containing the connection information.\n
     * This can be used to check the status of the connection encryption/pairing.
     */
    virtual void onAuthenticationComplete(ble_gap_conn_desc* desc);

    /**
     * @brief Called when using numeric comparision for pairing.
     * @param [in] pin The pin to compare with the client.
     * @return True to accept the pin.
     */
    virtual bool onConfirmPIN(uint32_t pin);
}; // NimBLEServerCallbacks

#endif /* CONFIG_BT_ENABLED && CONFIG_BT_NIMBLE_ROLE_PERIPHERAL */
#endif /* MAIN_NIMBLESERVER_H_ */
