import argparse
import socket
import select
import time
import random
from collections import deque
from sender import packHeader, unpackHeader
#constants for SYN,ACK,FIN bit math
SYN = 4
ACK = 2
FIN = 1
BIT16 = 65536
BIGNUMBER = 30000
class recvSeg:
    def __init__(self, num, data):
        self.num = num
        self.data = data

def main():
    #doing parsing of args
    parser = argparse.ArgumentParser()
    parser.add_argument("port", help="Port number of the socket on the server, like 3456")
    parser.add_argument("outName", help="the name of the text file into which the text sent by the sender should be stored")
    args = parser.parse_args()
    print args.port

    #sorting out message constants
    PORT = int(args.port)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM,0)#make udp socket
    s.bind(("",PORT))
    finished = False
    logList = [] #will hold alist of strings that will eventually become the log file for PingServer
    que = deque()


    print("waiting on response...")
    data, addr = s.recvfrom(2048)
    flag, segNum, ackNum = unpackHeader(data[:5])
    initTime = time.time()
    logList.append(["rcv",initTime,"S",segNum,0,ackNum])
    if flag != "SYN": #if it's an attempt to start file transfer, we boot up the handshake
        print "wrong flag, exiting."
        sys.exit()

    #we reply to handshake
    server_isn = random.randint(0,pow(2,16)-5)
    initHand = packHeader(True,True,False,server_isn%BIT16,segNum%BIT16) 
    s.sendto(initHand, addr)
    logList.append(["snd",time.time(),"SA",server_isn,0,segNum])

    data, addr = s.recvfrom(2048)
    flag, segNum, ackNum = unpackHeader(data[:5])
    logList.append(["rcv",time.time(),"A",segNum,0,ackNum])
    if flag != "ACK":
        print "wrong flag, exiting..." 
        sys.exit()
    initHand = packHeader(False,True,False,(server_isn + 1)%BIT16,segNum%BIT16)
    s.sendto(initHand,addr)
    logList.append(["snd",time.time(),"A",server_isn+1,0,segNum])
    server_isn += 1

    #Main loop where the data is received
#------------------------------------------------------------------------------------------------------------------------------------
#------------------------------------------------------------------------------------------------------------------------------------
#------------------------------------------------------------------------------------------------------------------------------------
    expectedAck = segNum
    finList = []
    garbo = []
    cDup = 0
    print "preparing to receive file"
#if incoming is correct, put it into final and update expectedAck, then check garbage list for potential expectedAck updates
#if incoming is not, throw it into a list
    
    while flag != "FIN": #should probs replace this with a true statement but ill do it later idk
        readable, writable, err = select.select([s],[s],[s])

        if que:    
            for sock in writable:
                poppedAck = que.pop()
                # print "Sending Ack for: ", poppedAck
                ackDataHead = packHeader(False,False,False,server_isn%BIT16,poppedAck%BIT16)
                sock.sendto(ackDataHead,addr)
                logList.append(["snd",time.time(),"A",server_isn,0,poppedAck])

        
        for sock in readable:
            data, addr = sock.recvfrom(2048) # just chill and print acks for now 
            flag, segNum, ackNum = unpackHeader(data[:5])
            while segNum + BIGNUMBER < expectedAck:
                segNum += BIT16

            if flag == "FIN":
                break
            logList.append(["rcv",time.time(),"D",segNum,len(data[5:]),ackNum])
            # print "Recieved data: ", data[5:]
            # print "Recieved acknum: ", segNum," Expected: ", expectedAck
            if segNum == expectedAck : #if the next packet is in order
                expectedAck += len(data[5:]) #update expectedAck to the next packet
                finList.append(data[5:])
                while 1: #now we check if any of the packets in garbo can be tacked onto the end of finlist
                    tempList = [x for x in garbo if x.num == expectedAck]  
                    if not tempList:#breaks the loop if there aren't any that can be tacked on
                        break
                    garbo = [x for x in garbo if x.num > expectedAck] #update garbo to all stuff that cannot be tacked on
                    expectedAck += len(tempList[0].data) #update expectedAck
                    finList.append(tempList[0].data)

            elif segNum > expectedAck : #if the next packet is too far ahead (so a packet has not arrived when it should have)
                if not any(x.num == segNum for x in garbo): #if we haven't recieved this packet yet, store it in garbo 
                    garbo.append(recvSeg(segNum, data[5:])) #we do not update expectedAck
                else: #otherwise just count the duplicate segmetn
                    cDup += 1
            else:#don't need to worry about ackNum < expectedAck since in that case we just do nothing (well we count the duplicate segment)
                cDup += 1
            


            que.appendleft(expectedAck)



    


#------------------------------------------------------------------------------------------------------------------------------------
#------------------------------------------------------------------------------------------------------------------------------------
#------------------------------------------------------------------------------------------------------------------------------------

    logList.append(["rcv",time.time(),"F",segNum,0,ackNum])
    print "Teardown request recieved, sending ACKFIN"
    
    # s.sendto(finAckHand,addr)
    finAckHand = packHeader(False,True,True,server_isn%BIT16,segNum%BIT16) 
    while 1:
        readable, writable, err = select.select([s],[s],[s])
        if len(writable):
            writable[0].sendto(finAckHand,addr)
            break
        else:
            print "waiting to send..."

    logList.append(["snd",time.time(),"FA",server_isn,0,segNum])

    print "Closing down socket..."
    # s.shutdown(socket.SHUT_RDWR)
    s.close()
    print "Data transfer finished! Writing file..."
    f = open(args.outName, 'w')
    f.write(''.join(finList))
    f.close()
    print "File successfully written! Writing logs"
    f = open("Reciever_log.txt", 'w')
    f.write("Action \ttime \ttype \tseq \tsize\tack\n")
    for line in logList:
        line[1] = str(round(line[1] - initTime,3))
        for obj in line:
            f.write(str(obj)+"\t")
            
        f.write("\n")

    f.write("Amount of (original) Data Received (in bytes): " + str(len(''.join(finList))) + "\n")
    f.write("Number of (original) Data Segments Received: " + str(len(finList))+ "\n")
    f.write("Number of duplicate segments received (if any): " + str(cDup) + "\n")
    f.close()
    print("FINISHED LOG")
    # while 1: 
    #     try:

    #         print data, addr
    #         flag, segNum, ackNum = unpackHeader(data[:5])
    #         print flag
    #         print segNum
    #         print ackNum
    #         s.sendtoto("ack"+ data[0],addr)
    #         #split data from header and put into array -- temp code
    #         final.append(data[1:])

    #     except KeyboardInterrupt:
    #         break


if __name__ == "__main__":
    main()