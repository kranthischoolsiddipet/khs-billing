package com.kranthischool.khsbilling.printer

import android.annotation.SuppressLint
import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothSocket
import android.content.Context
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.OutputStream
import java.nio.charset.Charset
import java.text.NumberFormat
import java.util.Locale
import java.util.UUID

class EscPosPrinterHelper(private val context: Context) {

    companion object {
        // Standard SerialPortServiceClass_UUID for SPP / Bluetooth Serial
        private val SPP_UUID: UUID = UUID.fromString("00001101-0000-1000-8000-00805F9B34FB")

        // ESC/POS Command bytes
        val ESC_INIT = byteArrayOf(0x1B, 0x40) // Initialize printer
        val ESC_ALIGN_LEFT = byteArrayOf(0x1B, 0x61, 0x00)
        val ESC_ALIGN_CENTER = byteArrayOf(0x1B, 0x61, 0x01)
        val ESC_ALIGN_RIGHT = byteArrayOf(0x1B, 0x61, 0x02)
        val ESC_BOLD_ON = byteArrayOf(0x1B, 0x45, 0x01)
        val ESC_BOLD_OFF = byteArrayOf(0x1B, 0x45, 0x00)
        val ESC_FEED_LINES = byteArrayOf(0x1B, 0x64, 0x03) // feed 3 lines
        val GS_CUT = byteArrayOf(0x1D, 0x56, 0x41, 0x10) // Cut paper (full cut)
    }

    private val bluetoothAdapter: BluetoothAdapter? by lazy {
        BluetoothAdapter.getDefaultAdapter()
    }

    @SuppressLint("MissingPermission")
    fun getPairedPrinters(): List<BluetoothDevice> {
        val adapter = bluetoothAdapter ?: return emptyList()
        if (!adapter.isEnabled) return emptyList()
        return adapter.bondedDevices.toList()
    }

    suspend fun printFeeReceipt(
        deviceAddress: String,
        schoolName: String = "KRANTHI HIGH SCHOOL",
        schoolAddress: String = "Siddipet, Telangana - 502103",
        receiptNo: String,
        date: String,
        studentName: String,
        studentClass: String,
        studentId: String,
        amountPaid: Double,
        balanceRemaining: Double,
        paymentMode: String,
        collectedBy: String
    ): Result<Boolean> = withContext(Dispatchers.IO) {
        val adapter = bluetoothAdapter ?: return@withContext Result.failure(Exception("Bluetooth not supported on this device"))
        if (!adapter.isEnabled) {
            return@withContext Result.failure(Exception("Bluetooth is turned off"))
        }

        var socket: BluetoothSocket? = null
        var outputStream: OutputStream? = null

        try {
            val device = adapter.getRemoteDevice(deviceAddress)
            socket = device.createRfcommSocketToServiceRecord(SPP_UUID)
            socket.connect()
            outputStream = socket.outputStream

            val charset = Charset.forName("CP437")
            val currencyFormatter = NumberFormat.getCurrencyInstance(Locale("en", "IN"))

            // Initialize
            outputStream.write(ESC_INIT)

            // Header (Centered)
            outputStream.write(ESC_ALIGN_CENTER)
            outputStream.write(ESC_BOLD_ON)
            outputStream.write("$schoolName\n".toByteArray(charset))
            outputStream.write(ESC_BOLD_OFF)
            outputStream.write("$schoolAddress\n".toByteArray(charset))
            outputStream.write("Ph: +91 94402 12345\n".toByteArray(charset))
            outputStream.write("--------------------------------\n".toByteArray(charset))

            // Title
            outputStream.write(ESC_BOLD_ON)
            outputStream.write("FEE PAYMENT RECEIPT\n".toByteArray(charset))
            outputStream.write(ESC_BOLD_OFF)
            outputStream.write("--------------------------------\n".toByteArray(charset))

            // Details (Left aligned)
            outputStream.write(ESC_ALIGN_LEFT)
            outputStream.write("Receipt No: $receiptNo\n".toByteArray(charset))
            outputStream.write("Date      : $date\n".toByteArray(charset))
            outputStream.write("Student   : $studentName\n".toByteArray(charset))
            outputStream.write("Class     : $studentClass\n".toByteArray(charset))
            outputStream.write("Adm/ID No : $studentId\n".toByteArray(charset))
            outputStream.write("--------------------------------\n".toByteArray(charset))

            // Amount summary
            val paidFormatted = String.format(Locale.ENGLISH, "Rs. %.2f", amountPaid)
            val balFormatted = String.format(Locale.ENGLISH, "Rs. %.2f", balanceRemaining)

            outputStream.write(ESC_BOLD_ON)
            outputStream.write("Amount Paid: $paidFormatted\n".toByteArray(charset))
            outputStream.write(ESC_BOLD_OFF)
            outputStream.write("Mode       : $paymentMode\n".toByteArray(charset))
            outputStream.write("Balance Due: $balFormatted\n".toByteArray(charset))
            outputStream.write("--------------------------------\n".toByteArray(charset))

            // Footer
            outputStream.write(ESC_ALIGN_CENTER)
            outputStream.write("Collected By: $collectedBy\n".toByteArray(charset))
            outputStream.write("Thank you for your timely payment!\n".toByteArray(charset))
            outputStream.write("Computer Generated Slip\n\n\n\n".toByteArray(charset))

            outputStream.flush()
            Result.success(true)
        } catch (e: Exception) {
            Result.failure(e)
        } finally {
            try {
                outputStream?.close()
                socket?.close()
            } catch (_: Exception) {}
        }
    }
}
